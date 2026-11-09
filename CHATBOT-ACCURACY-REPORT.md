# Timely Health / Iryax Chatbot
## Accuracy improvements and verification report

**Prepared:** 7 November 2026  
**Project:** Timely Health / Iryax website chatbot  
**Purpose:** Record the accuracy issues investigated, changes made, checks performed, and work that remains.

---

## Executive summary

The chatbot uses retrieval-augmented generation (RAG): it retrieves indexed website content and generates an answer from that evidence. The work recorded here focused on improving routing, grounding, concise answers, and separation between Timely Health and Iryax without replacing the existing RAG architecture.

Several concrete response failures were reproduced and corrected:

- Timely Health and Iryax content is kept separate in comparison answers.
- Timely Health “solutions” questions can be routed to its **Who We Serve** page when that is the intended destination.
- A yes/no question about Doctor Consultations no longer returns the whole Timely Health services catalog.
- Coworking Space feature questions are routed to Iryax’s detailed Workspace page rather than a short Timely Health overview card.
- Basic answers are intended to be concise, while explicit requests for features or detail allow a fuller answer.
- The chat widget’s quick-reply options were removed, and streamed text formatting was improved.

The exact Doctor Consultations and Coworking Space questions were verified against the running chat API after restarting the server so it loaded the updated code. The health endpoint reported `ok` and 333 indexed chunks during verification.

**Important limitation:** These are targeted fixes, not a complete accuracy audit of every page, question type, or synchronization path. No measured overall accuracy score is claimed.

## 1. Application overview

The application is a local FastAPI chatbot backed by ChromaDB retrieval and Ollama text generation. It also includes website scraping/synchronization and an embeddable browser chat widget. The README documents the project structure, configuration, local startup, and evaluation command.

Relevant implementation areas:

- [`app/rag/engine.py`](./app/rag/engine.py) — topic routing, retrieval, evidence checks, direct answers, and non-streaming response generation.
- [`app/rag/widget_chat.py`](./app/rag/widget_chat.py) — streaming chat behavior and the widget’s answer-generation instructions.
- [`frontend/chat-widget.js`](./frontend/chat-widget.js) — embedded chat interface and streamed answer rendering.
- [`data/website_pages.json`](./data/website_pages.json) — configured page URLs for Timely Health and Iryax.
- [`README.md`](./README.md) — setup, configuration, and operating instructions.

The configured source domains include `timelyhealth.in` and `iryax.com`. The chatbot must use each source for claims about its own organization rather than treating the two sites as one company.

## 2. Issues investigated and changes made

### 2.1 Timely Health versus Iryax domain confusion

**Problem:** Answers could blend Timely Health’s healthcare services with Iryax’s software and management products.

**Change:** Comparison prompts now require separate, explicitly labeled Timely Health and Iryax sections. The answer path checks that retrieval includes evidence from both configured domains before generating a cross-domain comparison. Source attribution instructions prohibit transferring a product or claim from one domain to the other.

**Verification recorded:** A comparison response was checked for separate organization sections and citations from both domains. A single-site Recruitment question was also checked to ensure it continued to describe Iryax.

### 2.2 “Solutions” routing

**Problem:** A question asking for Timely Health solutions could be confused with the audience groups on its Who We Serve page.

**Change:** Based on the requested product behavior, questions containing “solutions” can route to the configured Who We Serve page (`https://www.timelyhealth.in/whoweserve`). This page identifies groups served; it is not necessarily a catalog of healthcare services.

**Verification recorded:** The answer returned the Who We Serve groups and cited the `/whoweserve` page. The distinction between a list of healthcare services and a list of audiences should be retained when phrasing future questions and evaluating results.

### 2.3 Named service retrieval and the Doctor Consultations yes/no question

**Problem:** “Does Timely Health provide Doctor Consultations?” was interpreted as a request to list services because the question contained “provide.” The chatbot returned all six services instead of answering yes or no.

**Change:** The service-list classifier now excludes yes/no questions beginning with cues such as “does” or “can.” When an exact service heading is present in retrieved service-page records, the retrieval layer can return a short, source-backed availability answer. The same retrieval object is used by the regular and streaming chat paths.

**Verified live result:** “Yes. Timely Health provides Doctor Consultations.”  
**Source:** [`Timely Health services`](https://www.timelyhealth.in/service)

The first live retest still showed the old response because the running server had been started without code reload. Restarting the process loaded the current code; the same API question then returned the expected answer and source.

### 2.4 Coworking Space feature retrieval

**Problem:** “What features does the Coworking Space platform provide?” initially returned a single marketing line from Timely Health’s products overview. That overview is not the detailed feature source.

**Change:** Coworking Space questions now route to Iryax’s Workspace detail page unless the user explicitly names the Timely Health domain. “Coworking” is accepted as related to “workspace” for evidence coverage, and feature-focused instructions ask for distinct supported features instead of a generic summary.

**Verified live result:** The chatbot returned five concise bullets based on the Workspace page:

- Automatic calendar syncing and desk scheduling.
- Booking management, cabin capacities, and office layouts.
- Occupancy sensors and IoT integration.
- The Smart Workspace Control Panel.
- The Reservation Pipeline for room-usage tracking.

**Source:** [`Iryax Workspace`](https://iryax.com/workspace)

### 2.5 Concise answers and detail requests

**Problem:** Basic “What is X?” answers could be too long, while explicit requests for more detail should still receive useful information.

**Change:** Streaming and non-streaming prompts distinguish short/basic questions from explicit detail requests. Basic answers are guided toward concise descriptions; detail, feature, or follow-up questions can return more information from the retrieved section.

**Verification recorded:** A basic Recruitment question remained concise, while a “Tell me more” follow-up expanded. This is a targeted behavior check, not a complete measurement across every product.

### 2.6 Named Timely Health service sections

**Problem:** Similar headings and nearby service text could cause a named service question to retrieve the wrong section or be rejected despite supporting page content.

**Change:** Exact indexed heading matches take precedence over fuzzy matches, and named service questions are scoped to their relevant service section. Service attribution and grounding safeguards were added to both response paths.

**Verification recorded:** Named service questions were checked against the Timely Health services page. The indexed content includes information for services such as Second Opinions and Community Health Camps.

**Remaining quality note:** “Explain Second Opinions” can still produce overlapping wording across bullets. The answer instructions were tightened to discourage repeated facts, but this should remain part of future answer-quality testing.

### 2.7 Chat widget presentation

**Problem:** Quick-reply buttons appeared inside the chat conversation, and streamed answers needed clearer formatting.

**Change:** The quick-reply chips were removed from the chat panel. The widget renderer was updated to handle streamed bold text, labeled headings, and bullet lists while preserving existing input and header controls.

**Verification recorded:** JavaScript syntax, renderer behavior, external-link handling, and delivery of the updated widget from the running app were checked.

## 3. Verification summary

| Check | Result | Evidence/source |
|---|---|---|
| Timely Health / Iryax comparison | Separate sections and domain-specific source attribution were checked. | Timely Health About page and relevant Iryax pages |
| “What is Recruitment?” | Concise answer behavior was checked. | Iryax Recruitment page |
| Named Timely Health service questions | Service-page retrieval and section scoping were checked. | Timely Health services page |
| “Does Timely Health provide Doctor Consultations?” | Live API returned a direct yes answer after restarting the stale server. | `https://www.timelyhealth.in/service` |
| Timely Health solutions routing | The Who We Serve destination and audience list were checked. | `https://www.timelyhealth.in/whoweserve` |
| “What features does the Coworking Space platform provide?” | Live API returned five feature bullets from the detailed Workspace page. | `https://iryax.com/workspace` |
| Application health | `/health` returned status `ok`; the index reported 333 chunks at the time checked. | Local FastAPI health endpoint |
| Widget formatting | Syntax and targeted rendering behavior were checked. | `frontend/chat-widget.js` |

These checks are a set of focused examples. They should not be interpreted as a statistical accuracy score or proof that all answers are correct.

## 4. Current scope and known limitations

The following work is **not established as complete**:

1. **Full accuracy evaluation:** Not every configured page, service, product, or question style has been checked.
2. **Automated regression suite:** The checks described above were primarily targeted manual/API and inline checks. A maintained test suite covering these cases should be added.
3. **Website synchronization:** Automatic or scheduled synchronization was recommended for testing, but the end-to-end synchronization workflow was not verified as part of these fixes.
4. **Second Opinions phrasing:** The answer is grounded in the service page but can repeat or overlap details; further quality review is warranted.
5. **Current site content:** Website copy and indexed content can change. A correct answer depends on the crawl/index being current and on retrieval selecting the right source.
6. **Clinical advice:** This chatbot is an information interface to website content, not a medical decision-maker or substitute for professional care.

The user’s previously stated scores—7/10 for functionality and 5/10 for answer accuracy—were qualitative assessments, not measured evaluation results. This report does not revise them into numeric test scores.

## 5. Recommended next steps

1. Add automated regression cases for the exact Doctor Consultations and Coworking Space questions, including expected source URLs.
2. Add tests that distinguish “healthcare services,” “solutions,” “who do you serve,” and explicit list requests.
3. Build a small evaluation set covering Timely Health, Iryax, cross-domain comparisons, follow-ups, brief answers, and detailed answers.
4. Check answer support and citation correctness separately; a correct source URL alone does not guarantee a correct answer.
5. Test the website synchronization workflow and confirm changed page content reaches the index.
6. Review redundant phrasing on Second Opinions and other feature explanations.
7. Re-run the regression set after prompt, routing, scraping, or embedding/index changes.

## 6. Run and verify locally

On Windows, the project’s documented startup path is `start.bat`. When the server is available, open `http://127.0.0.1:8000`. The health endpoint is `http://127.0.0.1:8000/health`.

The server process must be restarted after code changes when it is running without auto-reload. Otherwise, tests against the live API may exercise stale code even when direct Python checks use the updated source.

## Conclusion

The specific routing and response issues documented here have targeted fixes, and the Doctor Consultations and Coworking Space behaviors were verified through the live API after restarting the server. The chatbot is improved for those cases, but broader accuracy and synchronization validation remain outstanding. The next confidence-building step is to turn these examples into repeatable regression tests and expand coverage across both website domains.
