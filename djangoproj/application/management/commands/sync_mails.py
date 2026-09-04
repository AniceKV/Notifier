import sys
from pathlib import Path
from email import policy
from email.parser import BytesParser
import imaplib
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

# 1. Allow importing from your project root and Ingestion folder
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "Ingestion") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "Ingestion"))

# Import your models
from application.models import Email, Topic, EmailMatch, UserMailbox

# Import your pipeline modules
from Ingestion.embedder import TextEmbedder
from Ingestion.similarity_filter import find_candidate_chunks, evaluate_chunk_similarities
from Ingestion.summarizer import evaluate_and_summarize
from Ingestion.email_parser import parse_email
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup


def clean_html(raw_html: str) -> str:
    """Strips HTML tags, styles, and scripts to leave pure readable text."""
    if not raw_html:
        return ""
    if "<" not in raw_html and ">" not in raw_html:
        return raw_html.strip()
    soup = BeautifulSoup(raw_html, "html.parser")
    for element in soup(["script", "style", "head", "title", "meta", "noscript"]):
        element.extract()
    return soup.get_text(separator=" ", strip=True)


class Command(BaseCommand):
    help = "Platform-agnostic IMAP email fetcher and AI relevance & notification pipeline."

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, default=None, help='Sync specifically for this user ID')
        parser.add_argument('--days', type=int, default=None, help='Optional override: look back N days instead of using last grabbed message timestamp')

    def handle(self, *args, **options):
        # Prevent Windows console UnicodeEncodeError on emojis/special characters
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        target_user_id = options.get('user_id')

        # 1. Look for configured mailboxes in database
        if target_user_id:
            mailboxes = list(UserMailbox.objects.filter(user_id=target_user_id, is_active=True))
        else:
            mailboxes = list(UserMailbox.objects.filter(is_active=True))

        if not mailboxes:
            self.stdout.write(self.style.WARNING("No active mailboxes configured. Connect one in your Profile."))
            return

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

        # 3. Process each mailbox
        for mailbox in mailboxes:
            user = mailbox.user
            topics = list(Topic.objects.filter(owner=user))
            if not topics:
                self.stdout.write(self.style.WARNING(f"User '{user.username}' has no topics configured. Skipping."))
                continue

            # Ensure all topics have valid cached embeddings matching current model dimensions
            for topic in topics:
                vec = topic.get_embedding_vector()
                if not vec or len(vec) != 768:
                    self.stdout.write(f"Generating 768-dim mpnet embedding for topic: {topic.name}")
                    topic_text = f"{topic.name}: {topic.description}"
                    topic.set_embedding_vector(TextEmbedder.embed_text(topic_text))
                    topic.save()

            # Connect to IMAP server (platform-agnostic)
            self.stdout.write(f"Connecting to {mailbox.platform} ({mailbox.imap_server}:{mailbox.imap_port}) for {user.username}...")
            try:
                mail = imaplib.IMAP4_SSL(mailbox.imap_server, mailbox.imap_port)
                mail.login(mailbox.email_address, mailbox.get_decrypted_password())
                mail.select("INBOX")
            except Exception as err:
                self.stderr.write(self.style.ERROR(f"Failed to connect to {mailbox.imap_server}: {err}"))
                continue

            # Look for the latest email already grabbed for this user & mailbox platform
            last_email = Email.objects.filter(owner=user, platform=mailbox.platform, received_at__isnull=False).order_by('-received_at').first()
            days_override = options.get('days')

            if "gmail" in mailbox.imap_server.lower():
                if days_override is not None:
                    query_str = f'"newer_than:{days_override}d"' if days_override > 0 else ""
                    self.stdout.write(f"Searching {mailbox.platform} (override: last {days_override} days)...")
                elif last_email and last_email.received_at:
                    since_ts = int(last_email.received_at.timestamp()) - 60  # 1-minute safety buffer
                    query_str = f'"after:{since_ts}"'
                    self.stdout.write(f"Searching {mailbox.platform} for all emails newer than last sync ({last_email.received_at.strftime('%Y-%m-%d %H:%M:%S')})...")
                else:
                    query_str = '"newer_than:7d"'
                    self.stdout.write(f"Initial sync: searching {mailbox.platform} for emails from last 7 days...")

                if query_str:
                    status, messages = mail.search(None, "X-GM-RAW", query_str)
                else:
                    status, messages = mail.search(None, "ALL")
            else:
                if days_override is not None:
                    if days_override > 0:
                        from django.utils import timezone
                        since_date = (timezone.now() - timedelta(days=days_override)).strftime("%d-%b-%Y")
                        query_str = f'(SINCE "{since_date}")'
                    else:
                        query_str = "ALL"
                    self.stdout.write(f"Searching {mailbox.platform} (override: last {days_override} days)...")
                elif last_email and last_email.received_at:
                    since_date = (last_email.received_at - timedelta(days=1)).strftime("%d-%b-%Y")
                    query_str = f'(SINCE "{since_date}")'
                    self.stdout.write(f"Searching {mailbox.platform} for all emails since {since_date} (last sync: {last_email.received_at.strftime('%Y-%m-%d %H:%M:%S')})...")
                else:
                    query_str = "ALL"
                    self.stdout.write(f"Initial sync: searching {mailbox.platform} for all emails...")

                status, messages = mail.search(None, query_str)

            if status != "OK" or not messages[0]:
                self.stdout.write(self.style.SUCCESS(f"No new emails found on {mailbox.platform}."))
                mail.logout()
                continue

            email_ids = messages[0].split()
            self.stdout.write(f"Found {len(email_ids)} email(s) on {mailbox.platform}. Fetching...")

            # 1. Fetch & parse emails to sort them chronologically (oldest -> newest)
            fetched_batch = []
            for e_id in email_ids:
                fetch_status, data = mail.fetch(e_id, "(BODY.PEEK[])")
                if fetch_status != "OK" or not data or not data[0]:
                    continue

                raw_bytes = data[0][1]
                parsed = parse_email(raw_bytes)

                # Extract headers for deduplication
                msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                message_id = msg.get("Message-ID") or f"{mailbox.platform.lower()}-{e_id.decode()}"

                # Early Deduplication
                if Email.objects.filter(message_id=message_id).exists():
                    safe_subj = parsed.get('subject') or "No Subject"
                    self.stdout.write(f"Skipping already stored email: {safe_subj}")
                    continue

                fetched_batch.append({
                    "e_id": e_id,
                    "message_id": message_id,
                    "parsed": parsed,
                })

            # Sort chronological (oldest -> newest) so notifications appear in order of arrival
            from django.utils import timezone
            def get_sort_key(item):
                dt = item["parsed"].get("received_at")
                if dt is None:
                    return timezone.now()
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt)
                return dt

            fetched_batch.sort(key=get_sort_key)
            self.stdout.write(f"Processing {len(fetched_batch)} new email(s) in chronological order...")

            for item in fetched_batch:
                parsed = item["parsed"]
                message_id = item["message_id"]

                # Step B: Store in Email table with platform identifier
                email_obj = Email.objects.create(
                    owner=user,
                    platform=mailbox.platform,
                    message_id=message_id,
                    sender=parsed.get("sender") or "Unknown",
                    subject=parsed.get("subject") or "No Subject",
                    body=parsed.get("body") or "",
                    received_at=parsed.get("received_at"),
                )
                self.stdout.write(self.style.SUCCESS(f"Stored [{mailbox.platform}] Email: {email_obj.subject}"))

                # Step C: Clean HTML & Prepend Subject for Rich Context
                body_html = parsed.get("body") or ""
                clean_body = clean_html(body_html)
                subject_str = parsed.get("subject") or ""
                full_text = f"Subject: {subject_str}\n\n{clean_body}".strip() if clean_body else subject_str

                chunks = splitter.split_text(full_text) if full_text else []

                if not chunks:
                    continue

                # Step D: Test against Topics (Ranked Candidate Filtering with Deduplication)
                self.stdout.write(f"\n" + "-" * 60)
                self.stdout.write(f"📧 Evaluating Email: \"{email_obj.subject}\"")
                self.stdout.write(f"   Sender: {email_obj.sender} | Platform: {mailbox.platform} | Chunks: {len(chunks)}")
                self.stdout.write("-" * 60)

                # 1. First Pass: Compute embedding similarity against all topics
                topic_candidates = []
                for topic in topics:
                    diag = evaluate_chunk_similarities(
                        topic_vector=topic.get_embedding_vector(),
                        chunks=chunks,
                        threshold=topic.similarity_threshold
                    )

                    candidates = diag["candidates"]
                    all_scores = diag["all_scores"]
                    scores_preview = ", ".join(f"{s:.3f}" for s in all_scores[:5])
                    if len(all_scores) > 5:
                        scores_preview += f", ... (+{len(all_scores) - 5} more)"

                    if not candidates:
                        self.stdout.write(self.style.WARNING(
                            f"  🎯 Topic: \"{topic.name}\" [Threshold: {topic.similarity_threshold:.3f}]\n"
                            f"     ❌ Stage 1 [Embedding Cosine]: FAILED\n"
                            f"        Max Score: {diag['max_score']:.4f} < Threshold: {topic.similarity_threshold:.3f}\n"
                            f"        All Chunk Scores: [{scores_preview}] (⏱️ {diag['elapsed_ms']}ms)"
                        ))
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f"  🎯 Topic: \"{topic.name}\" [Threshold: {topic.similarity_threshold:.3f}]\n"
                            f"     ✅ Stage 1 [Embedding Cosine]: PASSED\n"
                            f"        Top Score: {diag['max_score']:.4f} >= Threshold: {topic.similarity_threshold:.3f}\n"
                            f"        Passing Chunks: {diag['passed_count']}/{diag['total_chunks']} (Scores: [{scores_preview}]) (⏱️ {diag['elapsed_ms']}ms)"
                        ))
                        topic_candidates.append({
                            "topic": topic,
                            "diag": diag,
                            "best_chunk": candidates[0]["chunk"],
                            "best_score": candidates[0]["score"]
                        })

                if not topic_candidates:
                    continue

                # 2. Rank candidate topics by similarity score (highest score first)
                topic_candidates.sort(key=lambda x: x["best_score"], reverse=True)

                # 3. Stage 2: Evaluate with LLM on all candidate topics
                for candidate_info in topic_candidates:
                    cand_topic = candidate_info["topic"]
                    best_chunk = candidate_info["best_chunk"]
                    best_score = candidate_info["best_score"]

                    user_lm_url = user.profile.get_lm_studio_url() if hasattr(user, 'profile') else None
                    user_lm_model = user.profile.get_lm_studio_model() if hasattr(user, 'profile') else None
                    user_lm_key = user.profile.get_lm_studio_api_key() if hasattr(user, 'profile') else None

                    self.stdout.write(f"     🤖 Stage 2 [LM Studio: {user_lm_model}]: Evaluating candidate '{cand_topic.name}' (Score: {best_score:.4f})...")

                    is_relevant, summary_output, llm_diag = evaluate_and_summarize(
                        topic_name=cand_topic.name,
                        topic_desc=cand_topic.description,
                        email_subject=email_obj.subject,
                        email_body=best_chunk,
                        api_url=user_lm_url,
                        model=user_lm_model,
                        api_key=user_lm_key,
                        return_diagnostics=True
                    )

                    if not is_relevant:
                        self.stdout.write(self.style.WARNING(
                            f"     ❌ Stage 2 [LM Studio: {user_lm_model}]: REJECTED by AI for '{cand_topic.name}'\n"
                            f"        Reason: {llm_diag.get('reason', 'Deemed not genuinely relevant')}\n"
                            f"        Status: {llm_diag.get('status')} (⏱️ {llm_diag.get('elapsed_ms')}ms)"
                        ))
                        continue

                    self.stdout.write(self.style.SUCCESS(
                        f"     🎉 Stage 2 [LM Studio: {user_lm_model}]: VERIFIED RELEVANT to '{cand_topic.name}'! (⏱️ {llm_diag.get('elapsed_ms')}ms)\n"
                        f"        Top Score: {best_score:.4f}"
                    ))

                    # Save match to database (1 match record per (email, topic) pair)
                    match_obj, created = EmailMatch.objects.get_or_create(
                        email=email_obj,
                        topic=cand_topic,
                        defaults={
                            "user": user,
                            "candidate_score": best_score,
                            "matched_chunk": best_chunk,
                            "summary": summary_output,
                            "match_reason": f"Verified by AI as relevant to '{cand_topic.name}' (Cosine: {best_score:.4f})",
                        }
                    )
                    if created:
                        self.stdout.write(f"        💾 Saved EmailMatch #{match_obj.id}")
                    else:
                        match_obj.summary = summary_output
                        match_obj.candidate_score = best_score
                        match_obj.save()
                        self.stdout.write(f"        💾 Updated EmailMatch #{match_obj.id}")

                    # Send instant mobile push notification (ntfy.sh / Telegram)
                    from application.telegram_notifier import send_mobile_alert
                    sent = send_mobile_alert(
                        topic_name=cand_topic.name,
                        sender=email_obj.sender,
                        subject=email_obj.subject,
                        summary=summary_output,
                        platform=email_obj.platform,
                        received_at=email_obj.received_at,
                    )
                    if sent:
                        self.stdout.write(self.style.SUCCESS("        📲 Mobile push notification sent!"))

            mail.logout()

        self.stdout.write(self.style.SUCCESS("Finished processing mailboxes."))
