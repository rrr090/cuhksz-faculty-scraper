"""Group professors' free-text research fields into shared research interests.

Only some schools fill in the directory's "Academic Area" field, and the
research fields everyone else lists are free text that rarely repeats. Matching
those fields against this list gives every school shared topic pages, so the
vault links professors who work on the same things across schools.

Interests named like an official academic area share its page.
"""
from __future__ import annotations

import re

# (interest, pattern, schools it applies to; empty means every school)
_INTERESTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # Computing and AI
    ("Machine Learning", r"machine learning|deep learning|statistical learning|learning theory|representation learning|"
                         r"generative model|neural networks?|federated learning|online learning|transfer learning", ()),
    ("Reinforcement Learning", r"reinforcement learning|bandits?\b|sequential decision|markov decision", ()),
    ("Large Language Models", r"large language models?|\bllms?\b|language models?|foundation models?|multimodal models?", ()),
    ("Speech and Natural Language Processing", r"speech|natural language|\bnlp\b|computational linguistics|machine translation|"
                                               r"information retrieval|text mining|dialogue systems?", ()),
    ("Computer Vision", r"computer vision|image processing|image analysis|visual (?:computing|perception|recognition)|"
                        r"\bvideo\b|3d vision|pattern recognition|computer graphics", ()),
    ("Robotics", r"robot|embodied|autonomous (?:systems|driving|vehicles)|\bdrones?\b|\buavs?\b", ()),
    ("Trustworthy AI", r"trustworth|explainab|interpretab|fairness|ai safety|responsible ai|ai ethics|ai governance", ()),
    ("Security and Privacy", r"security|privacy|cryptograph|blockchain", ("sai", "sds", "sse")),
    ("Software Engineering", r"software", ()),
    ("Computer Systems and Networks", r"distributed (?:systems|computing)|cloud|high.performance computing|parallel computing|"
                                      r"computer architecture|operating systems?|databases?|computer networks?|networking|"
                                      r"internet of things|\biot\b|edge computing|\bgpu|ai infrastructure", ()),
    ("Algorithms and Theory", r"algorithm design|design (?:and analysis )?of algorithms|analysis and design of algorithms|"
                              r"algorithmic|approximation algorithms|combinatorial algorithms|graph algorithm|data structure|"
                              r"computational complexity|theoretical computer science|combinatori|graph theory", ()),
    ("Quantum Computing and Information", r"quantum (?:computing|computation|information|algorithms?|software)", ()),
    ("Data Mining and Analytics", r"data mining|big data|data science|data analytics|business analytics|data-driven", ()),
    # Mathematics and statistics
    ("Optimization and Operations Research", r"optimi[sz]ation|operations research|mathematical programming|integer programming|"
                                             r"supply chain|logistics|queueing|revenue management|game theory", ()),
    ("Statistics", r"statistic|time series|causal inference|survival analysis|bayesian|biostatistic", ()),
    ("Probability and Stochastic Processes", r"probability|stochastic|random matri|markov (?:processes|chains)", ()),
    ("Applied and Computational Mathematics", r"differential equations?|numerical|scientific computing|computational mathematics|"
                                              r"mathematical model|inverse problems?|applied mathematics|fluid dynamics", ()),
    ("Pure Mathematics", r"algebra|geometry|topology|number theory|mathematical analysis|harmonic analysis|spectral theory|"
                         r"representation theory|potential theory|functional analysis|dynamical systems", ()),
    # Engineering and physical sciences
    ("Communications and Signal Processing", r"wireless|signal processing|information theory|coding theory|telecommunication|"
                                             r"communication (?:systems|networks|theory)|\b[56]g\b|radar|antenna|satellite", ()),
    ("Electronics and Semiconductors", r"semiconductor|integrated circuit|\bvlsi\b|microelectronic|circuits?|\bchips?\b|"
                                       r"electronic devices?|micro-led|displays?|sensors?", ()),
    ("Photonics and Optics", r"photonic|optic|laser|metamaterial|plasmon|terahertz", ()),
    ("Energy", r"(?<!high.)energy|power systems?|smart grids?|batter(?:y|ies)|photovoltaic|solar|fuel cells?|electric vehicles?", ()),
    ("Control and Systems", r"control (?:theory|systems?|engineering)|cyber-physical|networked control|systems engineering", ()),
    ("Physics", r"physics|condensed matter|astrophysic|cosmolog|quantum (?:mechanics|field|materials|many-body)|"
                r"superconduct|tensor networks?", ()),
    ("Chemistry", r"chemi|catalys|organometallic|(?<!evidence )(?<!speech )synthesis|spectroscop|polymer", ()),
    ("Materials Science", r"materials?\b|nanomaterial|thin films?|2d materials|quantum dots?|perovskite", ()),
    # Life sciences and medicine
    ("Bioinformatics", r"bioinformatic|computational biology|genomic|systems biology|multi-omics|proteomic", ()),
    ("Biomedical Science & Engineering", r"biomedical engineering|biomaterial|medical devices?|biofabrication|tissue engineering|"
                                         r"medical imaging|medical robot|biosens|regenerative medicine|nanomedicine", ()),
    ("Biological Sciences", r"biology|molecular|(?<!solar )(?<!fuel )\bcells?\b|stem cell|protein|genetic|\bgenes?\b|immunolog|microbio|virolog", ()),
    ("Neuroscience", r"neuro|\bbrain\b", ()),
    ("Cancer Research", r"cancer|oncolog|tumou?r", ()),
    ("Metabolic and Cardiovascular Disease", r"metabolic|obesity|diabet|dyslipidemia|cardio|cardiac|vascular|hypertension", ()),
    ("Public Health", r"public health|epidemiolog|global health|health (?:policy|economics|services)|health care|healthcare|"
                      r"preventive|family medicine|general practice|\bage?ing\b|geriatric", ()),
    ("Pharmaceutical Science", r"pharma|drugs?\b", ()),
    ("Clinical Medicine", r"clinical|surgery|surgical|anesthes|anaesthes|nursing|ophthalm|orthop|pediatric|paediatric|"
                          r"psychiatr|radiolog|cardiolog|emergency medicine", ()),
    ("Medical Education", r"medical education", ()),
    # Business and economics
    ("Economics", r"econom|\blabou?r (?:economics|markets?)|international trade|industrial organi[sz]ation", ()),
    ("Finance", r"financ|asset pricing|capital markets?|banking|fintech|investment|corporate governance", ()),
    # Humanities and social sciences
    ("Linguistics and Translation", r"linguistic|language acquisition|phonolog|syntax|semantics|pragmatics|corpus|"
                                    r"translation|interpreting|bilingual|discourse|multimodality|language teaching", ("hss", "spp")),
    ("Literature", r"literature|literary|poetry|fiction|novel|modernism|drama|narrative", ("hss",)),
    ("History", r"histor", ("hss", "spp", "med")),
    ("Philosophy", r"philosoph|metaphysic|ethics|epistemolog|\blogic\b", ()),
    ("Politics and International Relations", r"politic|international relations|international security|public opinion|"
                                             r"diplomac|geopolitic|u\.s\.-china|china.s rise|nationalism|democra", ()),
    ("Public Policy and Governance", r"public policy|policy analysis|governance|public administration|government", ()),
    ("Urban Studies and Geography", r"urban|\bcit(?:y|ies)\b|planning|geograph|regional development|land use", ()),
    ("Sociology", r"sociolog|social stratification|inequalit|migration|demograph|famil(?:y|ies)|gender|social movements?|"
                  r"disability", ()),
    ("Psychology", r"psycholog|cognitive|cognition|mental health|well-?being|emotion", ()),
    ("Media and Communication", r"media|journalism|communication studies|film|cinema|advertising|public relations", ("hss", "spp")),
    ("Culture and Arts", r"cultur|art history|heritage|visual arts|religio|anthropolog", ("hss", "spp")),
    ("Education", r"education|pedagog|teaching|curricul|learning sciences", ("hss", "music", "spp")),
    ("Sports Science", r"sport|physical education|exercise", ()),
    ("Environment and Sustainability", r"environmental|and environment\b|sustainab|climate|ecolog|green infrastructure|"
                                       r"nature-based|(?:urban|climate) resilience", ()),
    # Music
    ("Piano and Keyboard", r"piano|keyboard|organ\b|harpsichord", ("music",)),
    ("Composition and Conducting", r"composition|conducting|music theory|solfeggio|orchestration", ("music",)),
    ("Strings", r"violin|viola|cello|double bass|harp\b|guitar|pipa|erhu|guzheng", ("music",)),
    ("Voice and Opera", r"soprano|tenor|baritone|mezzo|\bbass\b|voice|vocal|opera|stage director", ("music",)),
    ("Winds, Brass and Percussion", r"flute|oboe|clarinet|bassoon|\bhorn\b|trumpet|trombone|tuba|saxophone|percussion", ("music",)),
    ("Musicology", r"musicology|ethnomusicology|music history|traditional performing arts|chinese opera", ("music",)),
)

INTERESTS = tuple((name, re.compile(pattern, re.I), schools) for name, pattern, schools in _INTERESTS)


def research_interests(person: dict) -> list[str]:
    """Official academic areas first, then the interests matched from listed research fields."""
    found = list(dict.fromkeys(person["academic_area"]))
    fields = " ; ".join(person["research_field"])
    for name, regex, schools in INTERESTS:
        if name not in found and (not schools or set(schools) & set(person["schools"])) and regex.search(fields):
            found.append(name)
    return found
