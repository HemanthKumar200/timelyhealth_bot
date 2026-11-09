"""Streaming chat helpers that reuse the existing RAG engine."""
from __future__ import annotations

import re
import time

import ollama

from app.rag.engine import (
    EMBED_MODEL,
    LLM_MODEL,
    PAGES,
    ChatSession,
    Retrieval,
    context_body,
    answer_supported_by_context,
    context_covers_question,
    correct_service_attribution,
    detect_answer_length,
    exact_heading_keys,
    ground_named_service_answer,
    format_answer_markdown,
    handle_small_talk,
    infer_subject,
    is_detailed_request,
    is_cross_domain_comparison,
    is_brief_restatement,
    is_rephrase_request,
    is_catalog_list_question,
    is_offering_detail_question,
    partner_question_kind,
    partner_direct_answer,
    normalize_typos,
    numbers_are_grounded,
    page_host,
    prepare_chat_turn,
    rephrase_last_answer,
    retrieve,
    sources_supporting_answer,
)

NOT_FOUND = (
    "I don't have that information right now. "
    "You can contact the Timely Health team for help."
)
MEDICAL_SAFETY = (
    "I can't diagnose conditions or recommend medicines. "
    "If you have symptoms, please consult a doctor. "
    "If this is an emergency, call local emergency services immediately."
)
MEDICAL_RE = re.compile(
    r"\b(diagnos|prescri|dosage|dose|tablet|capsule|antibiotic|ibuprofen|"
    r"paracetamol|medicine|medication|symptom|chest pain|shortness of breath|"
    r"suicid|overdose|emergency|heart attack|stroke|allergic reaction|"
    r"should i take|what medicine)\b",
    re.I,
)

STREAM_NUM_CTX = 4096
STREAM_NUM_PREDICT = 320
STREAM_KEEP_ALIVE = "30m"
TOP_CHUNKS = 6


def is_medical_or_emergency(question: str) -> bool:
    return bool(MEDICAL_RE.search(question or ""))


def retrieve_compact(
    question: str,
    keys=None,
    intent="website_question",
    host="",
    preferred_urls=None,
    heading_hint="",
) -> Retrieval:
    retrieved = retrieve(
        question,
        keys=keys,
        intent=intent,
        host=host,
        preferred_urls=preferred_urls,
        heading_hint=heading_hint,
    )
    sources = list(retrieved.sources or [])[:TOP_CHUNKS]
    return Retrieval(
        context=retrieved.context or "",
        sources=sources,
        intent=retrieved.intent,
        mode=retrieved.mode,
        keys=list(retrieved.keys or []),
        direct_answer=retrieved.direct_answer or "",
    )


def build_stream_prompt(question: str, context: str, sources: list[str], history: list, detailed: bool) -> str:
    kind = partner_question_kind(question)
    if is_catalog_list_question(question) or kind == "benefits":
        style = (
            "List only the card titles as bullets, exactly as they appear. "
            "Do not add descriptions. Do not list Partner With Us as a benefit. "
            "Never write more than 8 lines."
        )
    elif kind == "form":
        style = (
            "Answer only about the partner form and the 24-hour reply. "
            "Do not list partner types. Do not mention membership."
        )
    elif kind == "who":
        style = (
            "Name every eligible group written in the context, including business "
            "if it appears. Write 'RWA leader' with no expansion in parentheses. "
            "If the user asked about a group that is not written there, say the "
            "page does not mention that group. Do not say they cannot partner. "
            "Do not say they can partner unless their group is named."
        )
    elif kind == "meaning":
        style = (
            "Say who Partner With Us is for and that it means collaborating "
            "on health initiatives, using only the retrieved wording."
        )
    elif is_cross_domain_comparison(question):
        style = (
            "Compare the organizations in exactly two labeled bullets: "
            "'Timely Health:' and 'Iryax:'. For each bullet, use only facts "
            "from that organization's own domain in the retrieved context. "
            "Describe Timely Health's healthcare focus and Iryax's software "
            "products only where those facts are supported by their pages. "
            "Do not transfer products or claims between organizations, and do "
            "not infer a corporate relationship."
        )
    elif re.search(r"\b(difference between|compare|versus)\b|\bvs\b", question, re.I):
        style = (
            "Compare the requested subjects using only the retrieved website "
            "content. Keep each subject's facts separate. Write 4 to 6 short lines."
        )
    elif is_company_overview_question(question):
        style = (
            "Answer in 2 short sentences copied from the about page. "
            "Do not add bullets. Do not invent feature names or services."
        )
    elif (
        exact_heading_keys(question) == ["services"]
        and is_offering_detail_question(question)
    ):
        style = (
            "Answer only about the specific Timely Health service named in the "
            "question. Use details under that service's heading only; ignore "
            "neighboring services. Attribute it to Timely Health, never Iryax. "
            "Use only facts in that service's retrieved text; do not add outcomes, "
            "reasons, or generic benefits. Answer with at most 4 concise bullets. "
            "Use one distinct fact per bullet; do not add an introductory summary "
            "or repeat the same fact in different words."
        )
    elif is_offering_detail_question(question) and re.search(
        r"\bfeatures?\b", normalize_typos(question)
    ):
        style = (
            "List the distinct features described in the retrieved section, "
            "with a short supporting detail for each. Ignore sample bookings, "
            "demo records, and promotional slogans. Do not invent benefits or "
            "repeat the same feature. Use at most 5 concise bullets."
        )
    elif detailed:
        style = (
            "Cover every point in the retrieved section. "
            "Answer in 5 to 8 short lines using only the retrieved website content. "
            "Do not stop after the first sentence. Never write more than 10 lines."
        )
    elif is_plain_what_is(question):
        style = (
            "Answer in one concise sentence of about 15 to 25 words, using the "
            "offering's page intro. Do not list features, plans, sub-products, "
            "or benefits unless the question explicitly asks for them."
        )
    elif is_offering_detail_question(question):
        style = (
            "Answer the question about this offering in up to 5 short lines. "
            "Include only relevant details from the retrieved section."
        )
    else:
        style = (
            "Answer in 1 to 2 concise sentences using only the retrieved website "
            "content. Never write more than 4 lines."
        )
    conversation = "\n".join(
        f"{message.get('role', 'user')}: {message.get('content', '')}"
        for message in (history or [])[-4:]
    )
    source_lines = "\n".join(sources) if sources else "Not available"
    return f"""
You are the Timely Health website assistant.

SAFETY:
- Do not diagnose medical conditions.
- Do not recommend medicines, doses, or treatments.
- For symptoms or emergencies, tell the user to consult a doctor or call emergency services.

SOURCE RULES:
- Answer only from the retrieved ChromaDB website context.
- Do not use external knowledge, training data, or assumptions.
- Attribute claims according to their source URL's domain. If the source is
  timelyhealth.in, do not attribute its services to Iryax.
- Do not invent products, prices, or policies.
- If the context does not contain a direct answer, reply exactly:
  "{NOT_FOUND}"
- Prefer named products and services from the retrieved context.
- Do not list generic marketing slogans.
- List only product or service names that appear in the retrieved context.
- If the context says there are several solutions but fewer names appear, list
  only the names that appear. Do not invent names.
- For cross-domain comparisons, keep claims tied to the source URL's domain.
  Use Timely Health facts only in the Timely Health section and Iryax facts
  only in the Iryax section. Do not infer that either organization owns,
  provides, or is affiliated with the other's products.
- If the user asks for a list of offerings and several named offerings appear
  in the context, list all of them.
- If the user asks for features, benefits, or how it helps, and the context
  already describes that offering, answer from that description.
  Do not say the information is missing just because the word "features" is absent.
- Never tell the user to Join as Member to become a partner.
- Never mention Join as Member unless the user asked about membership.
- Do not invent buttons, fees, hospitals, or approval guarantees.
- If asked about a form or enquiry, say yes only when the context has a form
  or "fill out the form". Do not list partner types for that question.
- Do not copy or continue the previous assistant answer. Answer only this question.
- Do not expand abbreviations such as RWA unless the context spells them out.
- "Within 24 hours" is when the team gets back to the applicant. Do not attach
  that timing to filling the form.
- For who/eligible/requirements, name the groups in the context. Do not answer
  with only the form.
- If asked about hospitals, clinics, startups, or schools and that word is
  absent, list the groups the page names and say the asked group is not
  mentioned. Never say "no they cannot become partners".
- Write RWA leader exactly. Never invent a meaning in parentheses.
- If asked about a fee, investment, documents, or guaranteed approval and
  those words are not in the context, reply exactly with the missing-info line.
- If no rupee/price figure is present in the context, do not guess a price.
- Never start with "Here's the answer" or similar filler.
- If the question is "what is X", describe X from the website context only.
  Do not give a generic dictionary definition.
- For a basic "what is X" question, give only a concise description of X.
  Do not list its features unless the user asks for features or detail.
- Do not append short ALL-CAPS marketing tags after product names.
- Use the conversation to stay on the same product or topic.
- If the user says "in brief", "more", or "features" without naming a new product,
  answer only about the latest topic in the conversation.
- Do not mention other products or the Complete Product Bundle unless asked.
- If the retrieved URL is iryax.com, describe that Iryax product. Do not say
  Timely Health provides it unless the retrieved text says so.
- Do not list partner-form dropdown options such as NGO or Non-Profit unless
  those words are in the Partner With Us copy.
- Do not paste the previous answer. If the user asks what something is used for,
  answer in 2 to 4 lines from the retrieved intro, then stop.
- Do not define medical camps as free or low-cost community care, or as
  bridging rural healthcare access, unless that wording is in the retrieved
  context. For iryax.com/camp, describe the management system and its listed
  features only.
- Ignore FAQ questions, buttons, sample camp listings, and demo/UI fragments; they are not features.
- Do not say "we organize" unless those words are in the context.
- Name the product features that appear in the context. Do not invent a community hall.
- Never write dictionary wording such as "X is a system/process that...".
- Never copy the conversation log. Never start a line with "user:" or "assistant:".

STYLE:
{style}
- Use simple English.
- Use bullets only for genuine lists.
- Do not repeat the question.
- Do not add a Source line; the server will attach sources.

CONVERSATION:
{conversation or "No previous conversation."}

USER QUESTION:
{question}

RETRIEVED WEBSITE CONTEXT:
{context}

SOURCE URLS:
{source_lines}

ANSWER:
"""


def stream_ollama(prompt: str):
    stream = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={
            "temperature": 0.0,
            "num_predict": STREAM_NUM_PREDICT,
            "num_ctx": STREAM_NUM_CTX,
        },
        keep_alive=STREAM_KEEP_ALIVE,
        stream=True,
    )
    for chunk in stream:
        text = (getattr(chunk, "message", None) and chunk.message.content) or ""
        if text:
            yield text


def limit_lines(text: str, max_lines: int = 8) -> str:
    lines = [line.rstrip() for line in (text or "").splitlines()]
    kept = [line for line in lines if line.strip()]
    return "\n".join(kept[:max_lines]).strip()


def drop_ungrounded_lead(answer: str, context: str) -> str:
    ctx = context_body(context).lower() if context else ""
    lines = [line for line in (answer or "").splitlines() if line.strip()]
    while lines and re.search(r"\bwe organize\b", lines[0], re.I) and "we organize" not in ctx:
        lines.pop(0)
    text = "\n".join(lines).strip()
    text = re.sub(r"(?i)\bfeature\s+\d+\s*", "", text).strip()
    text = re.sub(r"(?im)^(user|assistant)\s*:\s*.*$", "", text).strip()
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if re.search(
            r"low-cost|people in need|community care event|underserved|"
            r"outreach program that provides medical care|bridge the gap|"
            r"rural or remote|rural areas|remote areas",
            lower,
        ) and not re.search(r"rural|remote|low-cost|underserved", ctx):
            continue
        if "timely health" in lower and "timely health" not in ctx:
            sentence = re.sub(r"(?i)\s*,?\s*provided by timely health\s*(which is\s*)?", " ", sentence)
            sentence = re.sub(r"(?i)timely health('s)?", "Iryax", sentence)
        if re.search(r"\bin india\b", lower) and "india" not in ctx:
            sentence = re.sub(r"(?i)\s*,?\s*in india", "", sentence)
        if re.search(r"(?i)^(iryax global|this) is a\b", lower) and "iryax global is a" not in ctx:
            continue
        if re.search(r"healthcare technology company", lower) and "healthcare technology" not in ctx:
            continue
        if re.search(r"complete product bundle|hire smarter", lower) and "complete product bundle" not in ctx:
            continue
        if re.search(
            r"flu recovery|medical certificate|leave approvals dashboard|"
            r"family vacation|device synchronization below",
            lower,
        ):
            continue
        kept.append(sentence.strip())
    return " ".join(part for part in kept if part).strip()


def intro_from_context(context: str) -> str:
    overview = offering_overview_from_context(context)
    if overview:
        return overview.splitlines()[0]
    body = context_body(context)
    for sentence in re.split(r"(?<=[.!?])\s+", body or ""):
        cleaned = re.sub(r"(?i)\breimagined\b", " ", sentence)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-")
        words = cleaned.split()
        if len(words) >= 8:
            return " ".join(words[:28]).rstrip(",;:") + "."
    return ""


def offering_overview_from_context(context: str) -> str:
    """Build a fuller what-is answer from retrieved copy, skipping slogans and demo UI."""
    body = context_body(context)
    body = re.sub(r"(?i)\breimagined\b", " ", body)
    body = re.sub(
        r"(?i)\b(smart workplace coordinator|time & compensation|"
        r"present today|remote work|on leave|late / missing|"
        r"jane doe|mark smith|alex johnson|sarah williams|"
        r"all the features done right|frequently asked questions)\b",
        " ",
        body,
    )
    body = re.sub(r"(?i)\bfeature\s+\d+\.?\s*", " ", body)
    body = re.sub(r"([a-z])([A-Z])", r"\1 \2", body)
    body = re.sub(
        r"(?<=[a-z.])\s+((?:[A-Z][\w&/-]+)(?:\s+[A-Z][\w&/-]+){1,5})\s+",
        r". \1: ",
        body,
    )
    body = re.sub(r"\s+", " ", body)
    intro = []
    bullets = []
    seen = set()
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        cleaned = sentence.strip(" :-")
        if re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", cleaned, re.I):
            continue
        if re.search(
            r"(?i)\b(faq|unlock door|book now|leave approvals|flu recovery|"
            r"medical certificate|family vacation|device synchronization|"
            r"modular workforce|"
            r"no reservations active|members say|game-changer|"
            r"days remaining|cabins available|qr code|projector off|"
            r"leave hub|calendar active|leave claims|book demo)\b",
            cleaned,
        ):
            continue
        titled = re.match(
            r"^((?:[A-Z][\w&/-]+)(?:\s+[A-Z][\w&/-]+){1,3})(?::\s+|\s+)([a-z].+)$",
            cleaned,
        )
        if not titled:
            titled = re.match(
                r"^((?:[A-Z][\w&/-]+)(?:\s+[A-Z][\w&/-]+){1,3}):\s+(.+)$",
                cleaned,
            )
        if titled and len(titled.group(2).split()) >= 4:
            title = titled.group(1).strip()
            key = title.lower()
            if key not in seen:
                seen.add(key)
                desc = titled.group(2).strip(" :-")
                bullets.append(f"• {title}: {desc.rstrip('.')}.")
        else:
            words = cleaned.split()
            if 8 <= len(words) <= 36 and len(intro) < 1:
                intro.append(cleaned if cleaned.endswith(".") else cleaned + ".")
            elif (
                10 <= len(words) <= 40
                and len(bullets) < 5
                and not re.search(r"(?i)\b(organizer|talk to|join millions|members say)\b", cleaned)
            ):
                bullets.append(f"• {cleaned.rstrip('.')}.")
        if len(intro) + len(bullets) >= 7:
            break
    return "\n".join(intro + bullets)


def is_plain_what_is(question: str) -> bool:
    if re.search(r"\b(difference|compare|versus)\b|\bvs\b", question or "", re.I):
        return False
    return bool(re.search(r"\b(what is|what's|what are)\b", question or "", re.I))


def is_company_overview_question(question: str) -> bool:
    """'What is Timely Health?' is a company intro, not a feature list."""
    q = normalize_typos(question).strip()
    if re.search(
        r"\b(membership|products?|services?|solutions?|iryax|price|pricing|plan)\b",
        q,
    ):
        return False
    return bool(
        re.search(r"^(what is|what's|who is|tell me about)\s+timely health\b", q)
        and len(q.split()) <= 8
    )


def prefer_descriptive_intro(answer: str, question: str, context: str) -> str:
    if is_company_overview_question(question):
        return answer
    if re.search(r"\bmembership\b", question, re.I):
        return answer
    if not is_plain_what_is(question):
        return answer
    text = (answer or "").strip()
    slogan = bool(re.search(r"(?i)\breimagined\b|time & compensation|smart workplace coordinator", text))
    dictionary = bool(re.search(
        r"(?i)\bis a system that\b|\bis a process that\b|calculating and paying",
        text,
    ))
    messy = bool(re.search(r"[a-z][A-Z]", text)) and "•" not in text
    if slogan or dictionary or messy:
        intro = intro_from_context(context)
        if intro:
            return intro
    if text.lstrip().startswith("•"):
        intro = intro_from_context(context)
        if intro and intro.lower() not in text.lower():
            return intro
    return text


def iter_respond(session: ChatSession, question: str):
    """Yield SSE-ready dicts: token, done, or error. Reuses ChatSession memory."""
    started = time.perf_counter()
    retrieval_time = 0.0
    generation_time = 0.0
    sources: list[str] = []
    mode = "SMALL TALK"
    answer = handle_small_talk(question)

    if is_medical_or_emergency(question):
        answer = MEDICAL_SAFETY
        mode = "SAFETY"

    if answer is None and session.last_answer and (
        is_rephrase_request(question) or is_brief_restatement(question, session)
    ):
        answer = rephrase_last_answer(question, session.last_answer)
        sources = list(session.last_sources)
        mode = "REPHRASE"

    prompt = None
    context = ""
    retrieved = None
    standalone = question
    subject = session.current_subject
    if answer is None:
        standalone, keys, intent, subject, host = prepare_chat_turn(question, session)
        retrieval_start = time.perf_counter()
        list_q = is_catalog_list_question(question)
        retrieved = retrieve_compact(
            standalone,
            keys=keys,
            intent=intent or "website_question",
            host=host,
            preferred_urls=(
                None if list_q or is_offering_detail_question(standalone) else
                (list(session.last_sources) if session.last_sources else None)
            ),
            heading_hint="" if list_q or intent in {
                "all_products", "membership",
            } else subject,
        )
        retrieval_time = time.perf_counter() - retrieval_start
        context = (retrieved.context or "").strip()
        sources = list(retrieved.sources or [])[:TOP_CHUNKS]
        mode = retrieved.mode or "DYNAMIC SEMANTIC"
        expected_hosts = {
            page_host(PAGES.get(key, ""))
            for key in (keys or [])
            if PAGES.get(key)
        } if is_cross_domain_comparison(standalone, keys) else set()
        retrieved_hosts = {page_host(url) for url in sources}
        if expected_hosts and not expected_hosts.issubset(retrieved_hosts):
            answer = NOT_FOUND
            mode = "NOT_FOUND"
            sources = []
        elif retrieved.direct_answer:
            answer = format_answer_markdown(retrieved.direct_answer)
        elif not context:
            answer = NOT_FOUND
            mode = "NOT_FOUND"
            sources = []
        elif (grounded := partner_direct_answer(standalone, context)):
            answer = grounded
            if grounded == NOT_FOUND:
                mode = "NOT_FOUND"
                sources = []
        elif (
            re.search(r"\bwho can\b", standalone, re.I)
            and re.search(r"\b(camps?|provide|offer|run)\b", standalone, re.I)
            and not re.search(r"\bpartner", standalone, re.I)
            and not re.search(
                r"\b(rwa|provider|business|organisation|organization)\b",
                context,
                re.I,
            )
        ):
            answer = NOT_FOUND
            mode = "NOT_FOUND"
            sources = []
        elif not context_covers_question(standalone, context):
            answer = NOT_FOUND
            mode = "NOT_FOUND"
            sources = []
        elif (
            re.search(r"\bpartner", normalize_typos(standalone))
            and re.search(
                r"\b(fees?|free|investment|documents?|guaranteed?|application fee)\b",
                normalize_typos(standalone),
            )
            and not re.search(r"₹|\bfee\b|\bfree\b|\bdocument", context or "", re.I)
        ):
            answer = NOT_FOUND
            mode = "NOT_FOUND"
            sources = []
        else:
            prompt_history = session.history
            if detect_answer_length(question) == "brief" or re.search(
                r"in brief|briefly|in short|use of|used for|\bhow\b|\bwhat is\b|\bwhat are\b",
                question,
                re.I,
            ):
                prompt_history = []
            prompt = build_stream_prompt(
                standalone,
                context,
                sources,
                prompt_history,
                detailed=(
                    is_detailed_request(question)
                    or detect_answer_length(question) == "detailed"
                ),
            )

    pieces = []
    if prompt:
        generation_start = time.perf_counter()
        try:
            for token in stream_ollama(prompt):
                pieces.append(token)
                yield {"type": "token", "text": token}
        except Exception as exc:
            yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
            return
        generation_time = time.perf_counter() - generation_start
        streamed = "".join(pieces).strip()
        answer = limit_lines(streamed, 10) or streamed or NOT_FOUND
        cleaned = drop_ungrounded_lead(answer, context)
        if cleaned:
            answer = cleaned
        answer = prefer_descriptive_intro(answer, standalone, context) or answer
        answer = correct_service_attribution(answer, standalone, sources)
        answer = ground_named_service_answer(answer, standalone, context)
        if (
            context
            and is_plain_what_is(standalone)
            and not answer_supported_by_context(answer, context)
        ):
            answer = intro_from_context(context) or answer
        if context and not numbers_are_grounded(answer, context):
            answer = (
                "I couldn't confirm that exact figure from the website. "
                "Please check the Timely Health membership page or contact the team."
            )
            yield {"type": "replace", "text": answer}
        elif answer != streamed:
            yield {"type": "replace", "text": answer}
        if answer == NOT_FOUND:
            sources = []
        elif is_cross_domain_comparison(standalone, keys):
            sources = list(retrieved.sources or [])[:TOP_CHUNKS]
        else:
            sources = sources_supporting_answer(
                answer, context, sources, standalone
            )[:TOP_CHUNKS]
    else:
        yield {"type": "token", "text": answer}

    if mode not in {"SMALL TALK", "CLARIFY", "OUT OF SCOPE", "SAFETY"}:
        session.last_answer = answer
        session.last_sources = list(sources)
        if retrieved is not None:
            session.topics = list(getattr(retrieved, "keys", None) or session.topics)
            session.current_subject = infer_subject(
                standalone,
                session.topics,
                subject or session.current_subject,
            )
            if getattr(retrieved, "context", ""):
                session.last_context = retrieved.context
            if sources:
                session.current_host = page_host(sources[0])

    session.history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ])
    session.history = session.history[-6:]

    print(
        f"[CHAT] question={question[:80]!r} retrieve={retrieval_time:.2f}s "
        f"generate={generation_time:.2f}s total={time.perf_counter() - started:.2f}s "
        f"mode={mode} model={LLM_MODEL} embed={EMBED_MODEL}"
    )
    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "mode": mode,
    }
