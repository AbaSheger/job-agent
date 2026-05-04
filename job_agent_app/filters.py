from urllib.parse import urlparse

from .config import MAX_CANDIDATES_TO_SCORE, MAX_JOBS_PER_COMPANY


REPUTABLE_COMPANIES = [
    "spotify", "klarna", "tink", "mongodb", "elastic", "gitlab", "github",
    "atlassian", "canonical", "red hat", "docker", "cloudflare", "stripe",
    "wise", "revolut", "adyen", "booking.com", "shopify", "datadog",
    "microsoft", "google", "amazon", "aws", "apple", "meta", "netflix",
    "jetbrains", "miro", "automattic", "thoughtworks", "accenture",
]

BLOCKED_COMPANY_TERMS = [
    "jobgether", "crossover", "turing", "bairesdev", "outlier",
    "dataannotation", "data annotation", "remotasks", "toloka",
    "appen", "welocalize", "braintrust", "a.team",
]

BLOCKED_URL_DOMAINS = [
    "jobgether.com", "jooble.org", "jooble.com", "talent.com",
    "jobleads.com", "grabjobs.co", "workana.com", "upwork.com",
    "freelancer.com", "contra.com",
]

SPAM_TEXT_SIGNALS = [
    "commission only", "unpaid", "volunteer", "earn money", "side hustle",
    "no resume", "no cv", "join our talent pool", "talent pool",
    "future opportunities", "not an active opening", "ai trainer",
    "ai training", "data annotation", "microtask", "freelance marketplace",
]

REMOTE_EU_LOCATION_SIGNALS = [
    "sweden", "sverige", "stockholm", "europe", "european", "eu only",
    "eu-based", "eu based", "emea", "cet", "cest", "utc+1", "utc +1",
    "utc+2", "utc +2", "gmt+1", "gmt +1", "gmt+2", "gmt +2",
]

REMOTE_NON_EU_LOCATION_SIGNALS = [
    "us only", "usa only", "u.s. only", "united states only",
    "canada only", "north america only", "latin america only",
    "apac only", "india only", "philippines only",
]

TARGET_ROLE_BOOSTS = {
    "qa automation": 8,
    "test automation": 8,
    "automation engineer": 6,
    "automation developer": 6,
    "application support engineer": 7,
    "technical support engineer": 6,
    "integration developer": 8,
    "system developer": 8,
    "systemutvecklare": 8,
    "devops junior": 8,
    "cloud support engineer": 7,
    "technical consultant": 5,
    "support developer": 7,
    "systemförvaltare": 7,
    "systemforvaltare": 7,
    "förvaltare": 5,
    "forvaltare": 5,
    "utveckling": 4,
    "applikationsspecialist": 7,
    "sql/api": 6,
    "sql api": 6,
    "implementation consultant": 6,
}

TITLE_EXCLUDE = [
    "senior", "lead", "principal", "staff engineer", "manager",
    "architect", "arkitekt", "chef", "cto", "lia", "praktik",
    "praktikant", "internship", "examensjobb", "exjobb", "thesis",
]

TEXT_EXCLUDE = [
    "lead developer", "tech lead", "principal", "staff engineer",
    "head of engineering", "engineering manager", "developer manager",
    "team manager", "team lead", "cto", "architect", "arkitekt",
    "erfaren utvecklare", "erfaren systemutvecklare",
    "10+ years", "10 years experience", "8+ years", "8 years experience",
    "7+ years", "7 years experience", "15 years", "flera ars erfarenhet",
    "lia-praktik", "lia praktik", "larande i arbete", "lärande i arbete",
    "lia-student", "praktikplats", "praktikant", "student internship",
    "internship", "unpaid internship", "examensjobb", "examensarbete",
    "exjobb", "master thesis", "bachelor thesis",
]

MUST_PASS = [
    "develop", "developer", "engineer", "programmer", "programmerare",
    "utvecklare", "java", "python", "backend", "frontend", "fullstack",
    "devops", "testare", "qa", "quality assurance", "it-support", "it support",
    "software", "mjukvara", "data engineer", "cloud",
    ".net", "react", "angular", "supporttekniker",
    "applikationssupport", "application support", "technical support",
    "graduate", "trainee", "nyexaminerad", "junior",
] + list(TARGET_ROLE_BOOSTS)

ENTRY_LEVEL_SIGNALS = [
    "junior", "graduate", "trainee", "entry level", "entry-level",
    "nyexaminerad", "nyutexaminerad",
    "0-1 years", "0-2 years", "no experience",
]

LOCAL_MUNICIPALITIES = {
    "stockholm", "solna", "sundbyberg", "nacka", "lidingö", "lidingo",
    "huddinge", "botkyrka", "järfälla", "jarfalla", "täby", "taby",
    "danderyd", "sollentuna", "upplands väsby", "upplands vasby",
    "sigtuna", "norrtälje", "vallentuna", "österåker", "osteraker",
    "vaxholm", "uppsala", "gävle", "gavle", "sandviken", "hofors",
    "ockelbo", "falun", "ludvika", "borlänge", "borlange", "hedemora",
    "avesta", "säter", "sater", "mora", "orsa", "rättvik", "rattvik",
    "leksand", "malung", "älvdalen", "alvdalen", "vansbro", "gagnef",
    "smedjebacken",
}

LOCAL_COUNTIES = {
    "dalarna", "gävleborg", "gavleborg", "stockholms", "stockholm",
    "uppsala",
}

BASE_PRIORITY_BOOSTS = {
    "junior": 10,
    "nyexaminerad": 10,
    "nyutexaminerad": 10,
    "graduate": 8,
    "trainee": 8,
    "java": 7,
    "spring": 7,
    "backend": 6,
    ".net": 6,
    "c#": 6,
    "react": 5,
    "frontend": 4,
    "qa": 3,
    "devops": 2,
    "cloud": 2,
}


def is_location_eligible(job):
    if job.get("remote"):
        return is_remote_eligible(job)
    loc = job["location"].lower()
    return (
        any(municipality in loc for municipality in LOCAL_MUNICIPALITIES)
        or any(county in loc for county in LOCAL_COUNTIES)
    )


def job_url_domain(job):
    try:
        return urlparse(job.get("url", "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_reputable_company(company):
    normalized = company.lower()
    return any(company_name in normalized for company_name in REPUTABLE_COMPANIES)


def searchable_text(job, max_desc_chars=1200):
    return (
        f"{job['title']} {job['company']} {job['location']} "
        f"{job['desc'][:max_desc_chars]}"
    ).lower()


def is_low_quality_source(job):
    company = job["company"].lower()
    domain = job_url_domain(job)
    text = searchable_text(job)

    if any(term in company for term in BLOCKED_COMPANY_TERMS):
        return True
    if any(domain == blocked for blocked in BLOCKED_URL_DOMAINS):
        return True
    if any(domain.endswith("." + blocked) for blocked in BLOCKED_URL_DOMAINS):
        return True
    return any(signal in text for signal in SPAM_TEXT_SIGNALS)


def is_remote_eligible(job):
    if is_low_quality_source(job):
        return False

    text = searchable_text(job)
    if any(signal in text for signal in REMOTE_NON_EU_LOCATION_SIGNALS):
        return False
    if any(signal in text for signal in REMOTE_EU_LOCATION_SIGNALS):
        return True
    return is_reputable_company(job["company"])


def pre_filter(title, description):
    title_text = title.lower()
    text = (title + " " + description).lower()
    if any(keyword in title_text for keyword in TITLE_EXCLUDE):
        return False
    if any(keyword in text for keyword in TEXT_EXCLUDE):
        return False
    if any(keyword in title_text for keyword in ENTRY_LEVEL_SIGNALS):
        return True
    return any(keyword in text for keyword in MUST_PASS)


def candidate_priority(job):
    text = searchable_text(job, max_desc_chars=500)
    boosts = {**BASE_PRIORITY_BOOSTS, **TARGET_ROLE_BOOSTS}
    score = sum(weight for keyword, weight in boosts.items() if keyword in text)

    if job.get("remote"):
        score += 3
    if any(signal in text for signal in REMOTE_EU_LOCATION_SIGNALS):
        score += 4
    if is_reputable_company(job["company"]):
        score += 15
    if job["source"] == "Arbetsformedlingen":
        score += 8
    if is_low_quality_source(job):
        score -= 100
    return score


def diversify_candidates(candidates):
    selected = []
    company_counts = {}
    for job in candidates:
        company_key = job["company"].lower().strip()
        if company_counts.get(company_key, 0) >= MAX_JOBS_PER_COMPANY:
            continue
        selected.append(job)
        company_counts[company_key] = company_counts.get(company_key, 0) + 1
        if len(selected) >= MAX_CANDIDATES_TO_SCORE:
            break
    return selected

