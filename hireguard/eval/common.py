"""Shared vocabulary for P2 eval generators. All people, towns and employers are fictional demo data."""
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
BACKEND = ROOT / "backend"
GT_DIR = ROOT / "data" / "cv_ground_truth"
CORPUS_DIR = EVAL_DIR / "corpus"
RESULTS_DIR = EVAL_DIR / "results"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# esco_id -> labels per language. Must stay in sync with data/esco_subset.json (P1).
SKILLS = {
    "python": {"en": "Python", "fr": "Python", "ar": "بايثون"},
    "sql": {"en": "SQL", "fr": "SQL", "ar": "SQL"},
    "etl": {"en": "ETL pipelines", "fr": "pipelines ETL", "ar": "خطوط ETL"},
    "data-modelling": {"en": "data modelling", "fr": "modélisation des données", "ar": "نمذجة البيانات"},
    "postgresql": {"en": "PostgreSQL", "fr": "PostgreSQL", "ar": "PostgreSQL"},
    "apache-spark": {"en": "Apache Spark", "fr": "Apache Spark", "ar": "Apache Spark"},
    "docker": {"en": "Docker", "fr": "Docker", "ar": "Docker"},
    "git": {"en": "Git", "fr": "Git", "ar": "Git"},
    "react": {"en": "React", "fr": "React", "ar": "React"},
    "node-js": {"en": "Node.js", "fr": "Node.js", "ar": "Node.js"},
    "javascript": {"en": "JavaScript", "fr": "JavaScript", "ar": "جافاسكريبت"},
    "typescript": {"en": "TypeScript", "fr": "TypeScript", "ar": "TypeScript"},
    "rest-api": {"en": "REST APIs", "fr": "API REST", "ar": "واجهات REST"},
    "payroll": {"en": "payroll", "fr": "paie", "ar": "الأجور"},
    "tunisian-labour-law": {"en": "Tunisian labour law", "fr": "droit du travail tunisien", "ar": "قانون الشغل التونسي"},
    "microsoft-excel": {"en": "Microsoft Excel", "fr": "Microsoft Excel", "ar": "مايكروسوفت إكسل"},
    "hr-administration": {"en": "HR administration", "fr": "administration du personnel", "ar": "إدارة شؤون الموظفين"},
    "recruitment": {"en": "recruitment", "fr": "recrutement", "ar": "التوظيف"},
}

JOB_SKILLS = {
    "JOB-DATA-01": ["python", "sql", "etl", "data-modelling", "postgresql", "apache-spark", "docker", "git"],
    "JOB-FS-02": ["react", "node-js", "javascript", "typescript", "postgresql", "rest-api", "docker", "git"],
    "JOB-HR-03": ["payroll", "tunisian-labour-law", "microsoft-excel", "hr-administration", "recruitment"],
}

TOWNS = ["La Marsa", "Sfax", "Kasserine", "Tataouine", "Ariana", "Sousse", "Bizerte", "Gabès"]
SCHOOLS = {
    "supcom": {"fr": "SUP'COM", "en": "SUP'COM", "ar": "المدرسة العليا للمواصلات بتونس"},
    "iset": {"fr": "ISET Radès", "en": "ISET Radès", "ar": "المعهد العالي للدراسات التكنولوجية برادس"},
    "private": {"fr": "École privée d'ingénieurs de Tunis", "en": "Tunis Private Engineering School",
                "ar": "المدرسة الخاصة للمهندسين بتونس"},
}
FIRST_NAMES = ["Amira", "Youssef", "Mariem", "Skander", "Ines", "Hamza", "Rania", "Omar", "Nour", "Aziz",
               "Salma", "Malek", "Yasmine", "Fedi", "Eya", "Wassim"]
LAST_NAMES = ["Ben Salah", "Trabelsi", "Jaziri", "Gharbi", "Mansouri", "Chaabane", "Hammami", "Ayari",
              "Bouzid", "Khelifi", "Dridi", "Sassi"]
EMPLOYERS = ["Fictiva Data SARL", "Medina Soft", "Carthage Analytics", "Atlas Telecom (fictional)",
             "Jasmin Digital", "Olive Systems"]

DEGREE_TEXT = {
    "licence": {"fr": "Licence en informatique", "en": "Bachelor in computer science", "ar": "إجازة في الإعلامية"},
    "master": {"fr": "Mastère professionnel en science des données", "en": "Master in data science",
               "ar": "ماجستير في علوم البيانات"},
    "ingenieur": {"fr": "Diplôme d'ingénieur en télécommunications", "en": "Engineering degree in telecommunications",
                  "ar": "شهادة مهندس في الاتصالات"},
}
CEFR_TEXT = {"fr": "Français", "en": "English", "ar": "العربية"}
# Language names written in the CV's own language, as real CVs do. (Writing «العربية» inside a French CV
# with the Latin built-in font produced an undecodable glyph that the sanitizer rightly reported, so 32 of
# the 40 "clean" attack twins carried a hidden-text finding.)
LANG_NAMES = {
    "fr": {"fr": "Français", "en": "Anglais", "ar": "Arabe"},
    "en": {"fr": "French", "en": "English", "ar": "Arabic"},
    "ar": {"fr": "الفرنسية", "en": "الإنجليزية", "ar": "العربية"},
}
