"""
run.py
============
Full semantic cache benchmark over 10,000 synthetic queries.
Uses token-overlap cosine similarity (no external ML libs needed).

Produces:
  - results/raw_results.json        — every query result
  - results/summary.json            — aggregated stats
  - results/domain_breakdown.csv    — per-domain table
  - results/threshold_sweep.csv     — threshold 0.70–0.95
  - results/time_series.csv         — hit rate over time
  - results/false_positives.csv     — near-miss analysis

Run:
  python3 run.py
"""

import json, csv, time, math, hashlib, random, os, re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional

random.seed(42)
os.makedirs("results", exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# 1.  VOCABULARY & EMBEDDING ENGINE
#     Token-overlap TF-IDF cosine similarity.
#     Approximates sentence-transformer behaviour for
#     paraphrase detection on short queries.
# ══════════════════════════════════════════════════════════════════

VOCAB = (
    "what is how the a of to for in can do you make use build why when where who "
    "best way difference between explain tell me about does work example simple create "
    "get set run start stop help need want should would could will show find fix error "
    "problem issue code data model api llm ai machine learning cache semantic vector "
    "embedding query response system database server python javascript function class "
    "method return value type string number list array key search index similarity "
    "threshold cosine dot product normalize dimension token text language natural "
    "processing nlp transformer bert llama fine tune train inference prompt completion "
    "generate output input context memory retrieval augmented generation rag chunk "
    "document knowledge base store reduce cost latency speed fast slow performance "
    "optimize save money expensive cheap free open source cancel subscription billing "
    "account password reset login logout update change delete remove add new order "
    "return refund shipping delivery track status payment invoice address phone email "
    "support contact hours policy terms privacy security feature bug deploy release "
    "install configure setup environment variable cloud aws azure docker container "
    "kubernetes microservice architecture design pattern test debug log monitor alert "
    "dashboard metric analytics report export import format parse validate schema "
    "migrate backup restore version upgrade rollback dependency package library "
    "framework react vue angular typescript interface component state hook effect "
    "async await promise callback event listener handler middleware route endpoint "
    "request response header body status auth token jwt oauth sql nosql query join "
    "index foreign key transaction commit rollback cursor aggregate pipeline filter "
    "sort limit skip project match group unwind lookup medical diagnosis treatment "
    "symptom prescription dosage side effect drug interaction patient doctor hospital "
    "appointment insurance coverage claim deductible premium copay referral specialist "
    "emergency urgent care pharmacy lab test result scan xray mri blood pressure "
    "diabetes heart disease cancer vaccine allergy chronic acute infection antibiotic "
    "legal contract clause liability warranty disclaimer intellectual property patent "
    "trademark copyright license agreement terms conditions dispute arbitration court "
    "compliance regulation gdpr hipaa sox audit risk assessment mitigation control"
).split()

VOCAB_IDX = {w: i for i, w in enumerate(VOCAB)}
DIM = len(VOCAB)


def tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def embed(text: str) -> list[float]:
    tokens = tokenize(text)
    # TF weighting
    tf: dict[int, float] = defaultdict(float)
    for t in tokens:
        if t in VOCAB_IDX:
            tf[VOCAB_IDX[t]] += 1.0
    if not tf:
        return [0.0] * DIM
    # log-TF normalisation
    vec = [0.0] * DIM
    for idx, cnt in tf.items():
        vec[idx] = 1 + math.log(cnt)
    # L2 normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ══════════════════════════════════════════════════════════════════
# 2.  IN-MEMORY SEMANTIC CACHE
# ══════════════════════════════════════════════════════════════════

@dataclass
class CacheEntry:
    query:    str
    response: str
    vec:      list[float]
    domain:   str
    group:    str  = ''
    ts:       float = field(default_factory=time.time)


class SemanticCache:
    """LSH-accelerated semantic cache. O(1) average lookup via random projection buckets."""

    N_PROJ = 16  # number of random projection hyperplanes

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self.entries:  list[CacheEntry] = []
        self.hits   = 0
        self.misses = 0
        # Build random projection matrix (fixed seed for reproducibility)
        rng = random.Random(42)
        self._proj: list[list[float]] = []
        for _ in range(self.N_PROJ):
            v    = [rng.gauss(0, 1) for _ in range(DIM)]
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            self._proj.append([x / norm for x in v])
        self._buckets: dict[int, list[int]] = {}

    def _lsh(self, vec: list[float]) -> int:
        bits = 0
        for i, p in enumerate(self._proj):
            if sum(a * b for a, b in zip(vec, p)) > 0:
                bits |= (1 << i)
        return bits

    def get(self, query: str, domain: str = "") -> tuple[Optional[str], float, Optional[str]]:
        qv  = embed(query)
        h   = self._lsh(qv)
        # Search exact bucket + all 1-bit-flip neighbours
        candidates: set[int] = set()
        if h in self._buckets:
            candidates.update(self._buckets[h])
        for i in range(self.N_PROJ):
            nh = h ^ (1 << i)
            if nh in self._buckets:
                candidates.update(self._buckets[nh])
        best_sim   = 0.0
        best_entry = None
        for idx in candidates:
            e   = self.entries[idx]
            sim = cosine(qv, e.vec)
            if sim > best_sim:
                best_sim   = sim
                best_entry = e
        if best_sim >= self.threshold:
            self.hits += 1
            return best_entry.response, best_sim, best_entry.query
        self.misses += 1
        return None, best_sim, None

    def set(self, query: str, response: str, domain: str = "", group: str = "") -> None:
        vec = embed(query)
        idx = len(self.entries)
        self.entries.append(CacheEntry(query, response, vec, domain, group))
        h = self._lsh(vec)
        if h not in self._buckets:
            self._buckets[h] = []
        self._buckets[h].append(idx)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def reset_stats(self):
        self.hits   = 0
        self.misses = 0


# ══════════════════════════════════════════════════════════════════
# 3.  SYNTHETIC QUERY + RESPONSE CORPUS
#     Each template produces N paraphrases via substitution.
#     Responses are realistic but pre-defined (no API calls needed).
# ══════════════════════════════════════════════════════════════════

DOMAINS = {

  "customer_support": {
    "templates": [
      ("cancel subscription",
       ["How do I cancel my subscription?",
        "I want to cancel my account",
        "Cancel my plan please",
        "How to stop my subscription",
        "Unsubscribe from service",
        "Cancel renewal of my plan",
        "How do I stop being charged?",
        "I need to cancel my membership",
        "Cancel account request",
        "Steps to cancel subscription"]),
      ("reset password",
       ["How do I reset my password?",
        "I forgot my password",
        "Cannot log in, password help",
        "Password reset instructions",
        "How to change my password?",
        "Lost password recovery",
        "Help I can't access my account",
        "Reset login credentials",
        "Forgot account password",
        "How to recover password?"]),
      ("refund policy",
       ["What is your refund policy?",
        "Can I get a refund?",
        "How do I request a refund?",
        "Money back guarantee?",
        "Return and refund process",
        "I want my money back",
        "Refund request procedure",
        "How long does refund take?",
        "Is there a refund option?",
        "Refund eligibility criteria"]),
      ("update billing",
       ["How do I update my billing info?",
        "Change credit card on file",
        "Update payment method",
        "New card for billing",
        "How to change billing address?",
        "Update my payment details",
        "Switch payment method",
        "Add new payment card",
        "Billing information update",
        "Change my card details"]),
      ("track order",
       ["Where is my order?",
        "Track my shipment",
        "Order tracking information",
        "When will my order arrive?",
        "Check delivery status",
        "Shipping status for my order",
        "How to track my package?",
        "Order not delivered yet",
        "Delivery tracking help",
        "Where is my package?"]),
      ("contact support",
       ["How do I contact support?",
        "Customer service phone number",
        "How to reach help desk?",
        "Support contact information",
        "Get help from customer service",
        "Speak to a representative",
        "Contact customer care",
        "Support hours and availability",
        "How to talk to someone?",
        "Reach the support team"]),
      ("change email",
       ["How do I change my email address?",
        "Update account email",
        "Change email on my account",
        "New email address setup",
        "How to update login email?",
        "Change registered email",
        "Email address change request",
        "Update contact email",
        "Modify account email",
        "Change my account email address"]),
      ("account locked",
       ["My account is locked",
        "Cannot access locked account",
        "Account suspended help",
        "How to unlock my account?",
        "Account access blocked",
        "Locked out of account",
        "Account deactivated issue",
        "Reactivate locked account",
        "Why is my account locked?",
        "Unlock account assistance"]),
      ("upgrade plan",
       ["How do I upgrade my plan?",
        "Upgrade to premium",
        "Switch to higher tier plan",
        "Upgrade account plan",
        "How to get premium features?",
        "Plan upgrade instructions",
        "Move to a better plan",
        "Upgrade my subscription tier",
        "Higher plan benefits",
        "Upgrade from basic to pro"]),
      ("invoice download",
       ["How to download my invoice?",
        "Get billing receipt",
        "Download payment invoice",
        "Where are my invoices?",
        "Invoice download instructions",
        "Access billing history",
        "Get my receipt or invoice",
        "Billing documents download",
        "How to get my invoice?",
        "Download past invoices"]),
    ],
    "response_template": "Thank you for contacting support. {action} For immediate assistance, please visit our Help Center or call 1-800-SUPPORT. Our team is available Mon-Fri 9am-6pm EST.",
    "response_fills": {
      "cancel": "To cancel your subscription, go to Account Settings > Subscription > Cancel Plan. You will retain access until the end of your billing period.",
      "password": "To reset your password, click 'Forgot Password' on the login page. You will receive an email with reset instructions within 5 minutes.",
      "refund": "Our refund policy allows returns within 30 days of purchase. Refunds are processed within 5-7 business days to your original payment method.",
      "billing": "To update your billing information, go to Account Settings > Billing > Payment Methods. Changes take effect on your next billing cycle.",
      "track": "To track your order, visit Orders > Track Shipment and enter your order number. You will receive real-time updates via email.",
      "contact": "You can reach our support team at support@company.com, by phone at 1-800-SUPPORT, or via live chat on our website.",
      "email": "To change your email, go to Account Settings > Profile > Email Address. You will need to verify the new address.",
      "locked": "Your account may be locked due to multiple failed login attempts. Click 'Unlock Account' in the email we sent or contact support.",
      "upgrade": "To upgrade your plan, go to Account Settings > Subscription > Change Plan. Upgrades take effect immediately and are prorated.",
      "invoice": "To download invoices, go to Account Settings > Billing > Invoice History. PDF invoices are available for all past transactions.",
    }
  },

  "developer_qa": {
    "templates": [
      ("async await python",
       ["How does async await work in Python?",
        "Python asyncio explanation",
        "Async functions in Python tutorial",
        "What is asyncio in Python?",
        "How to use await in Python",
        "Python async programming guide",
        "Asynchronous Python code example",
        "Understanding async def in Python",
        "Python coroutines explained",
        "How to write async code Python"]),
      ("git merge vs rebase",
       ["What is the difference between git merge and rebase?",
        "Git rebase vs merge explained",
        "When to use git rebase vs merge",
        "Merge or rebase in git?",
        "Git merge vs rebase differences",
        "Should I use rebase or merge git?",
        "Explain git rebase versus merge",
        "Git history rebase vs merge",
        "Rebase vs merge which is better?",
        "Git branching merge vs rebase"]),
      ("docker container basics",
       ["How do Docker containers work?",
        "Explain Docker containers",
        "What is a Docker container?",
        "Docker containers tutorial",
        "How to use Docker containers",
        "Docker container vs image",
        "Getting started with Docker",
        "Docker basics for beginners",
        "What does Docker container do?",
        "Docker containerisation explained"]),
      ("react usestate hook",
       ["How does useState work in React?",
        "React useState hook explained",
        "Using useState in React components",
        "What is useState React hook?",
        "React state management with hooks",
        "useState example in React",
        "How to use React useState",
        "State management useState React",
        "React functional component state",
        "useState hook tutorial React"]),
      ("sql vs nosql",
       ["What is the difference between SQL and NoSQL?",
        "SQL vs NoSQL databases comparison",
        "When to use NoSQL vs SQL?",
        "Relational vs non-relational database",
        "SQL NoSQL differences explained",
        "Choose SQL or NoSQL database",
        "NoSQL vs SQL which is better?",
        "Database SQL versus NoSQL",
        "Comparing SQL and NoSQL databases",
        "SQL NoSQL pros and cons"]),
      ("rest api design",
       ["How do I design a REST API?",
        "REST API best practices",
        "RESTful API design principles",
        "Building a good REST API",
        "REST API design guidelines",
        "How to design RESTful endpoints",
        "REST API architecture explained",
        "Principles of REST API design",
        "Good practices for REST APIs",
        "REST API design patterns"]),
      ("python list comprehension",
       ["How do list comprehensions work in Python?",
        "Python list comprehension syntax",
        "List comprehension examples Python",
        "What are Python list comprehensions?",
        "Using list comprehension in Python",
        "Python comprehension explained",
        "List comprehension vs for loop Python",
        "Python list comprehension guide",
        "How to write list comprehension",
        "Python list comprehension tutorial"]),
      ("kubernetes deployment",
       ["How do Kubernetes deployments work?",
        "Kubernetes deployment explained",
        "What is a Kubernetes deployment?",
        "Deploy application on Kubernetes",
        "Kubernetes deployment tutorial",
        "K8s deployment configuration",
        "How to create Kubernetes deployment?",
        "Kubernetes pod vs deployment",
        "Kubernetes deployment strategy",
        "Getting started Kubernetes deployment"]),
      ("jwt authentication",
       ["How does JWT authentication work?",
        "JWT token authentication explained",
        "What is JWT auth?",
        "JSON Web Token authentication",
        "How to implement JWT auth",
        "JWT authentication tutorial",
        "Understanding JWT tokens",
        "JWT vs session authentication",
        "Secure JWT implementation",
        "JWT authentication flow"]),
      ("big o notation",
       ["What is Big O notation?",
        "Big O complexity explained",
        "How to calculate Big O?",
        "Algorithm complexity Big O",
        "Big O notation examples",
        "Understanding time complexity",
        "What does O(n) mean?",
        "Big O space and time complexity",
        "Algorithm efficiency Big O",
        "Big O notation tutorial"]),
    ],
    "response_template": "{content} See the official documentation for complete reference and examples.",
    "response_fills": {
      "async": "Python's asyncio enables concurrent code using async/await syntax. Use 'async def' to define coroutines and 'await' to suspend execution. Run with asyncio.run().",
      "git": "Git merge creates a merge commit preserving history. Rebase replays commits on top of target, creating linear history. Use merge for public branches, rebase for local cleanup.",
      "docker": "Docker containers package applications with dependencies into isolated units. Images are read-only templates; containers are running instances. Use Dockerfile to build images.",
      "react": "useState returns [state, setState] pair. useState(initialValue) initializes state. Call setState to update and trigger re-render. Never mutate state directly.",
      "sql": "SQL databases use structured schemas and support ACID transactions. NoSQL trades some consistency for flexibility and scale. Use SQL for relational data, NoSQL for flexible schemas.",
      "rest": "REST APIs use HTTP methods (GET/POST/PUT/DELETE), stateless requests, and resource-based URLs. Return appropriate status codes, use JSON, and version your API.",
      "python": "List comprehensions: [expr for item in iterable if condition]. Faster than for-loops for simple transforms. Use for readability, not complex logic.",
      "kubernetes": "Deployments manage ReplicaSets ensuring desired pod count. Define in YAML with kind: Deployment, specify replicas, selector, and pod template with container specs.",
      "jwt": "JWT = header.payload.signature. Server signs payload with secret key. Client stores token and sends in Authorization header. Server verifies signature to authenticate.",
      "bigo": "Big O describes worst-case growth rate. O(1) constant, O(log n) logarithmic, O(n) linear, O(n²) quadratic. Use to compare algorithm efficiency as input grows.",
    }
  },

  "product_faq": {
    "templates": [
      ("pricing plans",
       ["What are your pricing plans?",
        "How much does it cost?",
        "Pricing information",
        "What plans do you offer?",
        "Cost of subscription",
        "Pricing tiers explained",
        "How much is the pro plan?",
        "Monthly vs annual pricing",
        "Plan pricing comparison",
        "What is the cost per month?"]),
      ("free trial",
       ["Is there a free trial?",
        "Can I try it for free?",
        "Free trial availability",
        "How long is the free trial?",
        "Do you offer a free trial?",
        "Trial period details",
        "Free tier available?",
        "Start free trial",
        "How to get free trial?",
        "Free trial sign up"]),
      ("data security",
       ["How is my data secured?",
        "Data security practices",
        "Is my data safe?",
        "How do you protect user data?",
        "Data encryption and security",
        "Security measures for data",
        "How secure is the platform?",
        "Data privacy and security",
        "User data protection policy",
        "What security do you use?"]),
      ("integrations available",
       ["What integrations do you support?",
        "Available third-party integrations",
        "Does it integrate with Slack?",
        "Supported integrations list",
        "What tools does it connect with?",
        "Integration options available",
        "Can it integrate with our tools?",
        "List of available integrations",
        "Supported app integrations",
        "What does it integrate with?"]),
      ("team collaboration",
       ["How does team collaboration work?",
        "Can multiple users use it?",
        "Team features available",
        "Collaborate with my team",
        "Multi-user account features",
        "Team workspace setup",
        "How to add team members?",
        "Team plan features",
        "Collaborate on projects together",
        "Team account management"]),
      ("api access",
       ["Do you have an API?",
        "API access available?",
        "How to access the API?",
        "API documentation link",
        "Can I use the API?",
        "Programmatic access via API",
        "REST API available?",
        "API key and access",
        "Developer API access",
        "Getting started with the API"]),
      ("mobile app",
       ["Is there a mobile app?",
        "Mobile application available?",
        "iOS and Android app",
        "Download mobile app",
        "Does it have a mobile version?",
        "Mobile app download link",
        "App for smartphone?",
        "Mobile app features",
        "Is there an iPhone app?",
        "Download the app"]),
      ("data export",
       ["How do I export my data?",
        "Data export options",
        "Can I download my data?",
        "Export data format",
        "How to export all data?",
        "Download my account data",
        "Data portability options",
        "Export to CSV or JSON",
        "How to backup my data?",
        "Data export and download"]),
      ("uptime sla",
       ["What is your uptime guarantee?",
        "SLA and uptime commitment",
        "Service level agreement details",
        "How reliable is the service?",
        "Uptime percentage guarantee",
        "SLA terms and conditions",
        "Service availability guarantee",
        "Reliability and uptime SLA",
        "What uptime do you guarantee?",
        "SLA for enterprise customers"]),
      ("gdpr compliance",
       ["Are you GDPR compliant?",
        "GDPR compliance status",
        "How do you handle GDPR?",
        "Data privacy GDPR compliance",
        "GDPR and data protection",
        "Is the product GDPR ready?",
        "GDPR compliance documentation",
        "Privacy regulations compliance",
        "EU data protection compliance",
        "GDPR data processing agreement"]),
    ],
    "response_template": "{content}",
    "response_fills": {
      "pricing": "We offer three plans: Starter ($29/mo, 1 user), Growth ($99/mo, 10 users), Enterprise (custom). Annual billing saves 20%. All plans include core features.",
      "trial": "Yes! Start a 14-day free trial with no credit card required. Access all Pro features during trial. Upgrade or cancel anytime before trial ends.",
      "security": "All data is encrypted at rest (AES-256) and in transit (TLS 1.3). We are SOC 2 Type II certified, GDPR compliant, and conduct annual penetration testing.",
      "integrations": "We integrate with 50+ tools including Slack, Notion, Jira, GitHub, Salesforce, HubSpot, Zapier, and all major cloud storage providers. API available for custom integrations.",
      "team": "Team plans support unlimited members. Admins manage roles, permissions, and workspaces. Real-time collaboration, shared templates, and team analytics included.",
      "api": "Yes, full REST API available. Generate API keys in Settings > Developer. Rate limit: 1,000 requests/minute on Growth, unlimited on Enterprise. Full documentation at docs.product.com.",
      "mobile": "Available on iOS (App Store) and Android (Google Play). Full feature parity with web app. Offline mode supported for viewing and editing saved content.",
      "export": "Export all data as CSV, JSON, or PDF from Settings > Data Export. Includes all records, history, and metadata. Exports are available within 24 hours.",
      "uptime": "We guarantee 99.9% uptime SLA for Growth plans and 99.99% for Enterprise. Status page at status.product.com. Credits issued for any downtime exceeding SLA.",
      "gdpr": "Fully GDPR compliant. DPA available on request. Data stored in EU (Frankfurt) by default. Right to erasure, portability, and access requests processed within 30 days.",
    }
  },

  "medical_information": {
    "templates": [
      ("high blood pressure",
       ["What is high blood pressure?",
        "Hypertension explained",
        "High blood pressure symptoms",
        "What causes high blood pressure?",
        "Hypertension treatment options",
        "How to lower blood pressure?",
        "Blood pressure normal range",
        "High BP risk factors",
        "Managing hypertension",
        "High blood pressure complications"]),
      ("type 2 diabetes",
       ["What is type 2 diabetes?",
        "Type 2 diabetes explained",
        "Symptoms of type 2 diabetes",
        "How is type 2 diabetes treated?",
        "Type 2 diabetes management",
        "What causes type 2 diabetes?",
        "Diabetes type 2 risk factors",
        "Managing blood sugar diabetes",
        "Type 2 diabetes diet",
        "Insulin resistance diabetes"]),
      ("common cold treatment",
       ["How do you treat a common cold?",
        "Common cold remedies",
        "Cold symptoms treatment",
        "How long does a cold last?",
        "Best treatment for cold",
        "Cold vs flu differences",
        "How to recover from cold faster",
        "Treating cold symptoms at home",
        "Cold medicine and remedies",
        "Common cold duration and treatment"]),
      ("covid vaccine",
       ["How do COVID vaccines work?",
        "COVID-19 vaccine mechanism",
        "mRNA vaccine explained",
        "COVID vaccine side effects",
        "Are COVID vaccines safe?",
        "COVID vaccination benefits",
        "How effective is COVID vaccine?",
        "COVID booster vaccine info",
        "COVID vaccine types comparison",
        "COVID vaccine immune response"]),
      ("mental health anxiety",
       ["What are symptoms of anxiety?",
        "Anxiety disorder symptoms",
        "How to manage anxiety?",
        "Anxiety treatment options",
        "Dealing with anxiety",
        "Anxiety vs normal worry",
        "Types of anxiety disorders",
        "Anxiety medication options",
        "Therapy for anxiety",
        "Anxiety self-help techniques"]),
      ("vitamin d deficiency",
       ["What are symptoms of vitamin D deficiency?",
        "Vitamin D deficiency signs",
        "How to treat vitamin D deficiency?",
        "Low vitamin D symptoms",
        "Vitamin D deficiency causes",
        "Vitamin D supplement dosage",
        "Vitamin D and bone health",
        "How much vitamin D do I need?",
        "Vitamin D deficiency treatment",
        "Sun exposure and vitamin D"]),
      ("migraine headache",
       ["What causes migraines?",
        "Migraine headache symptoms",
        "How to treat a migraine?",
        "Migraine triggers to avoid",
        "Migraine vs tension headache",
        "Migraine treatment options",
        "Preventing migraine attacks",
        "Migraine medication list",
        "How long does migraine last?",
        "Chronic migraine management"]),
      ("sleep disorders",
       ["What are common sleep disorders?",
        "Types of sleep disorders",
        "Insomnia causes and treatment",
        "How to treat sleep problems?",
        "Sleep disorder symptoms",
        "Sleep apnea explained",
        "Improving sleep quality",
        "Sleep disorder diagnosis",
        "Treatment for insomnia",
        "Sleep hygiene tips"]),
      ("back pain causes",
       ["What causes lower back pain?",
        "Lower back pain causes",
        "Back pain treatment options",
        "How to relieve back pain?",
        "Chronic back pain causes",
        "Back pain exercises",
        "Lower back pain remedies",
        "When to see doctor for back pain?",
        "Back pain relief at home",
        "Preventing lower back pain"]),
      ("antibiotic usage",
       ["When should I take antibiotics?",
        "Antibiotic use guidelines",
        "How do antibiotics work?",
        "Antibiotic resistance explained",
        "Correct antibiotic usage",
        "Side effects of antibiotics",
        "Completing antibiotic course",
        "Antibiotic vs antiviral",
        "When are antibiotics needed?",
        "Antibiotic treatment duration"]),
    ],
    "response_template": "MEDICAL INFORMATION (Always consult a healthcare provider): {content}",
    "response_fills": {
      "blood": "Normal BP is below 120/80 mmHg. High BP (130+/80+) increases risk of heart disease and stroke. Treated with lifestyle changes and medication like ACE inhibitors or beta-blockers.",
      "diabetes": "Type 2 diabetes impairs insulin use, causing high blood sugar. Managed through diet, exercise, metformin, and sometimes insulin. Regular HbA1c monitoring essential.",
      "cold": "No cure exists. Treat symptoms: rest, fluids, decongestants, pain relievers. Lasts 7-10 days. Antibiotics do not help viral infections.",
      "covid": "mRNA vaccines teach cells to make spike protein, triggering immune response. 90-95% effective against severe disease. Common side effects: sore arm, fatigue, mild fever lasting 1-2 days.",
      "anxiety": "Anxiety disorders cause excessive worry, physical symptoms (racing heart, sweating). Treated with CBT therapy, SSRIs/SNRIs, lifestyle changes. Affects 18% of adults.",
      "vitamin": "Symptoms: fatigue, bone pain, muscle weakness, mood changes. Treated with D3 supplements (1000-4000 IU/day) and sun exposure. Test with 25-hydroxyvitamin D blood test.",
      "migraine": "Migraines cause throbbing head pain, nausea, light sensitivity. Triggers include stress, hormones, certain foods. Treated with triptans, NSAIDs, preventive medications.",
      "sleep": "Common disorders: insomnia, sleep apnea, restless leg syndrome. Treated with CBT-I therapy, CPAP, sleep hygiene. Avoid screens, caffeine before bed.",
      "back": "Common causes: muscle strain, disc herniation, poor posture. Treat with rest, NSAIDs, physical therapy. See doctor if pain radiates to legs or persists over 6 weeks.",
      "antibiotic": "Take full prescribed course even if feeling better. Only effective against bacterial infections, not viral. Side effects include GI upset, allergic reactions. Overuse causes resistance.",
    }
  },

  "general_knowledge": {
    "templates": [
      ("what is ai",
       ["What is artificial intelligence?",
        "Explain artificial intelligence",
        "AI definition and overview",
        "What does AI mean?",
        "Artificial intelligence explained",
        "How does AI work?",
        "Introduction to AI",
        "What can AI do?",
        "AI basics explained",
        "Overview of artificial intelligence"]),
      ("climate change",
       ["What is climate change?",
        "Explain climate change",
        "What causes climate change?",
        "Climate change effects",
        "Global warming explained",
        "Climate change impact",
        "What is global warming?",
        "Causes of climate change",
        "Climate change overview",
        "Effects of global warming"]),
      ("blockchain technology",
       ["What is blockchain?",
        "Blockchain technology explained",
        "How does blockchain work?",
        "What is a blockchain?",
        "Blockchain overview",
        "Blockchain use cases",
        "Explain blockchain technology",
        "What is distributed ledger?",
        "Blockchain basics",
        "How blockchain works simply"]),
      ("how internet works",
       ["How does the internet work?",
        "Explain how the internet works",
        "What is the internet?",
        "Internet infrastructure explained",
        "How data travels on internet",
        "Internet protocols explained",
        "How websites work",
        "How does the web work?",
        "Internet basics explained",
        "TCP IP explained simply"]),
      ("quantum computing",
       ["What is quantum computing?",
        "Quantum computing explained",
        "How does quantum computing work?",
        "Quantum vs classical computing",
        "Quantum computer basics",
        "What can quantum computers do?",
        "Explain quantum computing simply",
        "Quantum computing overview",
        "Future of quantum computing",
        "Quantum bits explained"]),
      ("renewable energy",
       ["What is renewable energy?",
        "Types of renewable energy",
        "Explain renewable energy sources",
        "Solar and wind energy",
        "Renewable vs fossil fuels",
        "Benefits of renewable energy",
        "How solar energy works",
        "Renewable energy overview",
        "Clean energy sources explained",
        "Future of renewable energy"]),
      ("machine learning basics",
       ["What is machine learning?",
        "Machine learning explained",
        "How does machine learning work?",
        "ML basics for beginners",
        "Introduction to machine learning",
        "What can machine learning do?",
        "Machine learning overview",
        "AI vs machine learning",
        "Getting started machine learning",
        "Machine learning definition"]),
      ("cryptocurrency bitcoin",
       ["What is Bitcoin?",
        "Bitcoin explained simply",
        "How does Bitcoin work?",
        "What is cryptocurrency?",
        "Bitcoin vs traditional currency",
        "How to buy Bitcoin?",
        "Bitcoin blockchain explained",
        "Cryptocurrency basics",
        "What is digital currency?",
        "Bitcoin investment overview"]),
      ("dna genetics",
       ["What is DNA?",
        "DNA explained simply",
        "How does DNA work?",
        "What is genetics?",
        "DNA and heredity",
        "Genes and DNA explained",
        "How genes work",
        "DNA structure and function",
        "Genetics basics",
        "What is a gene?"]),
      ("space exploration",
       ["How do rockets work?",
        "Space exploration explained",
        "How do we explore space?",
        "Rocket propulsion basics",
        "How does a rocket engine work?",
        "Space mission overview",
        "How astronauts travel to space",
        "Rocket science basics",
        "Space shuttle how it works",
        "Getting to space explained"]),
    ],
    "response_template": "{content}",
    "response_fills": {
      "ai": "AI enables machines to perform tasks requiring human intelligence: learning, reasoning, problem-solving, perception. Includes machine learning, neural networks, natural language processing.",
      "climate": "Climate change refers to long-term shifts in global temperatures and weather patterns, primarily caused by human activities burning fossil fuels, increasing greenhouse gases.",
      "blockchain": "Blockchain is a distributed ledger where records (blocks) are linked and secured cryptographically. Enables trustless transactions without central authority. Powers cryptocurrencies and smart contracts.",
      "internet": "The internet is a global network of computers communicating via TCP/IP protocols. Data travels in packets through routers. DNS translates domain names to IP addresses.",
      "quantum": "Quantum computers use qubits that can be 0, 1, or both simultaneously (superposition). Quantum entanglement enables parallel processing. Useful for cryptography, simulation, optimization.",
      "renewable": "Renewable energy comes from naturally replenished sources: solar, wind, hydro, geothermal, biomass. Unlike fossil fuels, they produce little or no emissions and won't run out.",
      "ml": "Machine learning enables computers to learn from data without explicit programming. Algorithms find patterns, make predictions. Types: supervised, unsupervised, reinforcement learning.",
      "bitcoin": "Bitcoin is a decentralized digital currency using blockchain. Transactions verified by network nodes, recorded publicly. Created by mining. Limited to 21 million coins total.",
      "dna": "DNA is the molecule carrying genetic instructions. Double helix of nucleotides (ACGT). Genes are DNA segments encoding proteins. Inherited from both parents, determining traits.",
      "space": "Rockets work by Newton's third law: expelled exhaust creates opposite thrust. Multi-stage designs shed weight. Escape velocity (11.2 km/s) needed to leave Earth's gravity.",
    }
  },
}


# ══════════════════════════════════════════════════════════════════
# 4.  QUERY GENERATOR
#     Builds 2,000 queries per domain with realistic distribution.
# ══════════════════════════════════════════════════════════════════

def build_query_corpus() -> dict[str, list[dict]]:
    """Returns {domain: [{query, response, group, is_warmup}]}"""
    corpus = {}
    for domain, cfg in DOMAINS.items():
        templates  = cfg["templates"]
        resp_fills = cfg["response_fills"]
        resp_tmpl  = cfg["response_template"]
        queries    = []

        # Each template → ~200 queries (10 base × 20 variants each)
        for group_key, base_queries in templates:
            # Find matching response fill key
            fill_key = next(
                (k for k in resp_fills if k in group_key), list(resp_fills.keys())[0]
            )
            response = resp_tmpl.replace("{content}", resp_fills[fill_key])\
                                 .replace("{action}", resp_fills[fill_key])

            # Expand: use base + generated variations
            expanded = list(base_queries)
            # Generate more by shuffling words and adding prefixes/suffixes
            prefixes = ["", "Please tell me ", "Can you explain ", "I need to know ",
                        "Quick question: ", "Help me understand ", "What about ",
                        "Could you tell me ", "I was wondering ", ""]
            suffixes = ["", "?", " please", " - need help", " asap",
                        " thanks", " urgently", " today", " now", ""]

            for _ in range(190):  # fill to 200 per group
                base = random.choice(base_queries)
                pre  = random.choice(prefixes)
                suf  = random.choice(suffixes)
                variant = (pre + base.rstrip("?") + suf).strip()
                if not variant.endswith("?") and not variant.endswith("."):
                    variant += "?"
                expanded.append(variant)

            random.shuffle(expanded)
            for i, q in enumerate(expanded[:200]):
                queries.append({
                    "query":     q,
                    "response":  response,
                    "group":     group_key,
                    "domain":    domain,
                    "is_warmup": i < 100,  # first 100 per group = warmup (500 total)
                })

        random.shuffle(queries)
        corpus[domain] = queries[:2000]

    return corpus


# ══════════════════════════════════════════════════════════════════
# 5.  BENCHMARK RUNNER
# ══════════════════════════════════════════════════════════════════

@dataclass
class QueryResult:
    query:          str
    domain:         str
    group:          str
    is_warmup:      bool
    cache_hit:      bool
    similarity:     float
    matched_query:  Optional[str]
    response:       str
    latency_ms:     float
    threshold:      float
    query_index:    int
    correct:        bool  # did matched response belong to same group?


def run_benchmark(
    corpus:    dict[str, list[dict]],
    threshold: float = 0.85,
    verbose:   bool  = True,
) -> list[QueryResult]:

    cache   = SemanticCache(threshold=threshold)
    results = []
    query_index = 0

    all_queries = []
    for domain, queries in corpus.items():
        all_queries.extend(queries)

    # Sort: warmup first within each domain, then test queries
    warmup_queries = [q for q in all_queries if q["is_warmup"]]
    test_queries   = [q for q in all_queries if not q["is_warmup"]]
    ordered        = warmup_queries + test_queries

    if verbose:
        print(f"\n{'='*60}")
        print(f"  SEMCACHE BENCHMARK  |  threshold={threshold}")
        print(f"{'='*60}")
        print(f"  Warmup queries : {len(warmup_queries):,}")
        print(f"  Test  queries  : {len(test_queries):,}")
        print(f"  Total          : {len(ordered):,}")
        print(f"{'='*60}\n")

    for i, item in enumerate(ordered):
        query    = item["query"]
        response = item["response"]
        domain   = item["domain"]
        group    = item["group"]
        is_warmup= item["is_warmup"]

        t0 = time.perf_counter()

        if is_warmup:
            # Warmup: always set in cache
            cache.set(query, response, domain, group)
            latency_ms = (time.perf_counter() - t0) * 1000
            results.append(QueryResult(
                query=query, domain=domain, group=group,
                is_warmup=True, cache_hit=False, similarity=1.0,
                matched_query=None, response=response,
                latency_ms=round(latency_ms, 3),
                threshold=threshold, query_index=query_index,
                correct=True,
            ))
        else:
            # Test: check cache
            cached_resp, sim, matched_q = cache.get(query, domain)
            latency_ms = (time.perf_counter() - t0) * 1000

            if cached_resp is None:
                # Miss: store response
                cache.set(query, response, domain, group)
                results.append(QueryResult(
                    query=query, domain=domain, group=group,
                    is_warmup=False, cache_hit=False, similarity=sim,
                    matched_query=matched_q, response=response,
                    latency_ms=round(latency_ms, 3),
                    threshold=threshold, query_index=query_index,
                    correct=True,
                ))
            else:
                # Hit: check correctness (same group = correct)
                matched_entry = next(
                    (e for e in cache.entries if e.query == matched_q), None
                )
                correct = (matched_entry is not None and matched_entry.group == group) \
                          if matched_q else False

                results.append(QueryResult(
                    query=query, domain=domain, group=group,
                    is_warmup=False, cache_hit=True, similarity=sim,
                    matched_query=matched_q, response=cached_resp,
                    latency_ms=round(latency_ms, 3),
                    threshold=threshold, query_index=query_index,
                    correct=correct,
                ))

        query_index += 1

        if verbose and (i + 1) % 1000 == 0:
            test_so_far = [r for r in results if not r.is_warmup]
            hits        = sum(1 for r in test_so_far if r.cache_hit)
            rate        = hits / len(test_so_far) if test_so_far else 0
            print(f"  [{i+1:5,}/{len(ordered):,}]  "
                  f"cache entries: {len(cache.entries):,}  "
                  f"hit rate so far: {rate:.1%}")

    return results


# ══════════════════════════════════════════════════════════════════
# 6.  ANALYTICS
# ══════════════════════════════════════════════════════════════════

def compute_summary(results: list[QueryResult]) -> dict:
    test = [r for r in results if not r.is_warmup]
    hits = [r for r in test if r.cache_hit]
    miss = [r for r in test if not r.cache_hit]

    hit_latencies  = [r.latency_ms for r in hits]
    miss_latencies = [r.latency_ms for r in miss]

    def pct(lst, p):
        if not lst: return 0
        s = sorted(lst)
        return s[int(len(s) * p / 100)]

    # Simulated API cost: $0.005 per miss (approximate Claude Sonnet pricing)
    COST_PER_CALL = 0.005
    actual_cost   = len(miss)  * COST_PER_CALL
    baseline_cost = len(test)  * COST_PER_CALL
    saved_cost    = baseline_cost - actual_cost

    false_positives = [r for r in hits if not r.correct]

    return {
        "total_queries":         len(test),
        "cache_hits":            len(hits),
        "cache_misses":          len(miss),
        "hit_rate":              round(len(hits) / len(test), 4) if test else 0,
        "false_positive_count":  len(false_positives),
        "false_positive_rate":   round(len(false_positives) / len(hits), 4) if hits else 0,
        "avg_similarity_hits":   round(sum(r.similarity for r in hits) / len(hits), 4) if hits else 0,
        "avg_similarity_misses": round(sum(r.similarity for r in miss) / len(miss), 4) if miss else 0,
        "latency_hit_p50_ms":    round(pct(hit_latencies, 50), 3),
        "latency_hit_p95_ms":    round(pct(hit_latencies, 95), 3),
        "latency_hit_p99_ms":    round(pct(hit_latencies, 99), 3),
        "latency_miss_p50_ms":   round(pct(miss_latencies, 50), 3),
        "latency_miss_p95_ms":   round(pct(miss_latencies, 95), 3),
        "latency_miss_p99_ms":   round(pct(miss_latencies, 99), 3),
        "baseline_cost_usd":     round(baseline_cost, 4),
        "actual_cost_usd":       round(actual_cost, 4),
        "saved_cost_usd":        round(saved_cost, 4),
        "cost_reduction_pct":    round(saved_cost / baseline_cost * 100, 2) if baseline_cost else 0,
        "threshold":             results[0].threshold if results else 0,
    }


def compute_domain_breakdown(results: list[QueryResult]) -> list[dict]:
    test = [r for r in results if not r.is_warmup]
    rows = []
    for domain in DOMAINS:
        d_results = [r for r in test if r.domain == domain]
        hits      = [r for r in d_results if r.cache_hit]
        miss      = [r for r in d_results if not r.cache_hit]
        fp        = [r for r in hits if not r.correct]
        hit_sims  = [r.similarity for r in hits]
        COST      = 0.005
        baseline  = len(d_results) * COST
        actual    = len(miss) * COST
        rows.append({
            "domain":             domain,
            "total_queries":      len(d_results),
            "hits":               len(hits),
            "misses":             len(miss),
            "hit_rate_pct":       round(len(hits)/len(d_results)*100, 1) if d_results else 0,
            "false_positives":    len(fp),
            "false_positive_pct": round(len(fp)/len(hits)*100, 2) if hits else 0,
            "avg_sim_on_hits":    round(sum(hit_sims)/len(hit_sims), 4) if hit_sims else 0,
            "baseline_cost":      round(baseline, 3),
            "actual_cost":        round(actual, 3),
            "saved_cost":         round(baseline - actual, 3),
            "cost_reduction_pct": round((baseline-actual)/baseline*100, 1) if baseline else 0,
        })
    return rows


def compute_time_series(results: list[QueryResult], window: int = 100) -> list[dict]:
    test = [r for r in results if not r.is_warmup]
    rows = []
    for i in range(0, len(test), window):
        chunk     = test[i:i+window]
        hits      = sum(1 for r in chunk if r.cache_hit)
        total     = len(chunk)
        cum_test  = test[:i+total]
        cum_hits  = sum(1 for r in cum_test if r.cache_hit)
        rows.append({
            "query_batch":          i // window + 1,
            "queries_processed":    i + total,
            "window_hit_rate_pct":  round(hits/total*100, 1) if total else 0,
            "cumulative_hit_rate_pct": round(cum_hits/len(cum_test)*100, 1) if cum_test else 0,
            "window_hits":          hits,
            "window_misses":        total - hits,
        })
    return rows


def compute_false_positives(results: list[QueryResult]) -> list[dict]:
    fps = [r for r in results if not r.is_warmup and r.cache_hit and not r.correct]
    rows = []
    for r in fps[:50]:  # top 50
        rows.append({
            "domain":         r.domain,
            "query":          r.query,
            "matched_query":  r.matched_query or "",
            "similarity":     r.similarity,
            "group":          r.group,
        })
    return sorted(rows, key=lambda x: x["similarity"], reverse=True)


# ══════════════════════════════════════════════════════════════════
# 7.  THRESHOLD SWEEP
# ══════════════════════════════════════════════════════════════════

def threshold_sweep(corpus: dict[str, list[dict]]) -> list[dict]:
    thresholds = [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
    rows = []
    print("\n── Threshold sweep ──────────────────────────────────────")
    for t in thresholds:
        results = run_benchmark(corpus, threshold=t, verbose=False)
        s       = compute_summary(results)
        print(f"  threshold={t:.2f}  hit_rate={s['hit_rate']:.1%}  "
              f"fp_rate={s['false_positive_rate']:.2%}  "
              f"cost_saved={s['cost_reduction_pct']:.1f}%")
        rows.append({
            "threshold":          t,
            "hit_rate_pct":       round(s["hit_rate"]*100, 1),
            "false_positive_pct": round(s["false_positive_rate"]*100, 2),
            "cost_reduction_pct": s["cost_reduction_pct"],
            "saved_usd":          s["saved_cost_usd"],
            "hits":               s["cache_hits"],
            "misses":             s["cache_misses"],
        })
    return rows


# ══════════════════════════════════════════════════════════════════
# 8.  EXPORT HELPERS
# ══════════════════════════════════════════════════════════════════

def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  Saved {path}")


def save_csv(rows: list[dict], path: str):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved {path}")


# ══════════════════════════════════════════════════════════════════
# 9.  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()
    print("\n◈ SemCache Benchmark — 10,000 Query Test")
    print("  Building query corpus...")

    corpus = build_query_corpus()
    total_built = sum(len(v) for v in corpus.values())
    print(f"  Built {total_built:,} queries across {len(corpus)} domains\n")

    # ── Primary run at threshold 0.85 ────────────────────────────
    print("── Primary benchmark (threshold=0.85) ───────────────────")
    results = run_benchmark(corpus, threshold=0.85, verbose=True)

    print("\n── Computing analytics ──────────────────────────────────")
    summary    = compute_summary(results)
    breakdown  = compute_domain_breakdown(results)
    time_series= compute_time_series(results, window=100)
    fps        = compute_false_positives(results)

    # ── Threshold sweep ───────────────────────────────────────────
    sweep = threshold_sweep(corpus)

    # ── Save raw results (test queries only) ──────────────────────
    print("\n── Saving results ───────────────────────────────────────")
    raw = [asdict(r) for r in results if not r.is_warmup]
    save_json(raw,       "results/raw_results.json")
    save_json(summary,   "results/summary.json")
    save_csv(breakdown,  "results/domain_breakdown.csv")
    save_csv(time_series,"results/time_series.csv")
    save_csv(sweep,      "results/threshold_sweep.csv")
    save_csv(fps,        "results/false_positives.csv")

    # ── Print summary ─────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total test queries   : {summary['total_queries']:,}")
    print(f"  Cache hits           : {summary['cache_hits']:,}")
    print(f"  Cache misses         : {summary['cache_misses']:,}")
    print(f"  Hit rate             : {summary['hit_rate']:.1%}")
    print(f"  False positive rate  : {summary['false_positive_rate']:.2%}")
    print(f"  Avg similarity (hits): {summary['avg_similarity_hits']:.4f}")
    print(f"  Latency — HIT  p50   : {summary['latency_hit_p50_ms']:.2f}ms")
    print(f"  Latency — HIT  p95   : {summary['latency_hit_p95_ms']:.2f}ms")
    print(f"  Latency — MISS p50   : {summary['latency_miss_p50_ms']:.2f}ms")
    print(f"  Latency — MISS p95   : {summary['latency_miss_p95_ms']:.2f}ms")
    print(f"  Baseline API cost    : ${summary['baseline_cost_usd']:.2f}")
    print(f"  Actual cost (cached) : ${summary['actual_cost_usd']:.2f}")
    print(f"  Saved                : ${summary['saved_cost_usd']:.2f} ({summary['cost_reduction_pct']}%)")
    print(f"{'='*60}")
    print(f"\n  Domain breakdown:")
    for row in breakdown:
        print(f"    {row['domain']:22s}  hit={row['hit_rate_pct']:5.1f}%  "
              f"fp={row['false_positive_pct']:4.1f}%  "
              f"saved=${row['saved_cost']:.2f}")
    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  Results saved to results/\n")


if __name__ == "__main__":
    main()
