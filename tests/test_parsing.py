"""Parsing tests. All names and addresses are made up; markup mirrors each school's template."""
import pytest

from cuhksz_faculty.config import School
from cuhksz_faculty.faculty import appointment, base_name, merge_duplicates, parse_cards, parse_profile, pick_rank
from cuhksz_faculty.sites import rank_links, site_urls

SCHOOL = School("abc", "School of Examples", "https://abc.example.edu")


def card(title, body=""):
    return f'<div class="list-content"><div class="list-text"><div class="list-title">{title}</div>{body}</div></div>'


FULL_CARD = card(
    '<a href="/en/teacher/7">DOE, Alex (By Courtesy)</a>',
    """<div class="list-des">Assistant Professor</div>
    <div class="list-des">Ph.D., Example University<br/>Young Fellow</div>
    <div class="list-area"><span>Academic Area: </span>Machine Learning, Robotics</div>
    <div class="list-area"><span>Research Field: </span>Control, and Planning</div>
    <div class="list-email"><span>Email: </span>alex@example.edu</div>
    <div class="list-website"><span>Personal Website: </span><a href="https://alex.example.org">https://alex.example.org</a></div>""",
)

PROFILE = """
<div class="block block-system">
  <div class="sub-title"><span>Biography</span></div><p>Alex studies robots.</p>
  <div class="sub-title"><span>Email</span></div><p>real@example.edu</p>
</div>
<div class="block"><div class="footer-1-0">Contact Us Email: office@example.edu Copyright</div></div>
"""


def test_card_with_directory_profile():
    [record] = parse_cards(FULL_CARD, SCHOOL)
    assert record["id"] == "abc-7"
    assert record["rank"] == "Assistant Professor"
    assert record["credentials"] == ["Ph.D., Example University", "Young Fellow"]
    assert record["academic_area"] == ["Machine Learning", "Robotics"]
    assert record["research_field"] == ["Control", "Planning"]
    assert record["email"] == "alex@example.edu"
    assert record["website"] == "https://alex.example.org"
    assert record["profile_url"] == "https://abc.example.edu/en/teacher/7"
    assert record["schools"] == ["abc"]


def test_name_linking_to_personal_site_becomes_the_website():
    [record] = parse_cards(card('<a href="https://myweb.example.edu/sam">Sam Lee</a>'), SCHOOL)
    assert record["profile_url"] == ""
    assert record["website"] == "https://myweb.example.edu/sam"
    assert record["id"].startswith("abc-")


def test_faculty_slug_urls_are_profiles():
    [record] = parse_cards(card('<a href="/en/faculty/sam-lee">Prof. Sam LEE</a>'), SCHOOL)
    assert record["id"] == "abc-sam-lee"
    assert record["profile_url"].endswith("/en/faculty/sam-lee")


def test_javascript_links_are_ignored():
    [record] = parse_cards(card('<a href="javascript:void(0)">Sam Lee</a>'), SCHOOL)
    assert record["website"] == "" and record["profile_url"] == ""


def test_rank_in_an_unlabelled_email_block():
    body = """<div class="list-des">Laureate in Chemistry; Member of an Academy</div>
    <div class="list-email">Visiting Professor</div>
    <div class="list-email"><span>Email: </span>a@example.edu</div>"""
    [record] = parse_cards(card('<a href="/en/teacher/1">A</a>', body), SCHOOL)
    assert record["rank"] == "Visiting Professor"
    assert record["email"] == "a@example.edu"


@pytest.mark.parametrize("lines, expected", [
    (["Founding Dean, Professor Emeritus", "Composer", "Professor"], "Professor"),
    (["Associate Dean of the School, Professor, Director of an Institute"], "Professor"),
    (["Former Professor at Elsewhere", "Assistant Professor"], "Assistant Professor"),
    (["X.Y. Example Presidential Chair Professor", "Former Professor with Tenure"], "X.Y. Example Presidential Chair Professor"),
    (["Composer"], "Composer"),
    ([], ""),
])
def test_pick_rank(lines, expected):
    assert pick_rank(lines) == expected


def test_parse_profile_splits_sections_and_stops_at_footer():
    assert parse_profile(PROFILE) == {"Biography": "Alex studies robots.", "Email": "real@example.edu"}


def test_name_helpers():
    assert base_name("LIU, Sam（By Courtesy）") == "LIU, Sam"
    assert base_name("Prof. Sam LEE") == "Sam LEE"
    assert appointment("LIU, Sam（By Courtesy）") == "By Courtesy"
    assert appointment("LIU, Sam") == ""


def person(pid, name, school, email="", website="", sections=None):
    return {"id": pid, "display": name, "schools": [school], "email": email, "website": website, "sections": sections or {},
            "profile_url": "", "source": "", "academic_area": [], "research_field": [], "credentials": []}


def test_same_person_in_two_schools_is_merged():
    merged = merge_duplicates([person("a-1", "LEE, Sam", "a", "sam@example.edu"), person("b-9", "Sam Lee", "b", "SAM@example.edu", sections={"Biography": "x"})])
    assert len(merged) == 1
    assert merged[0]["schools"] == ["a", "b"]
    assert merged[0]["sections"] == {"Biography": "x"}


def test_shared_assistant_email_does_not_merge_different_people():
    assert len(merge_duplicates([person("a-1", "LEE, Sam", "a", "office@example.edu"), person("b-2", "CHEN, Wei", "b", "office@example.edu")])) == 2


def test_same_name_with_different_contacts_stays_separate():
    assert len(merge_duplicates([person("a-1", "LI, Ming", "a", "one@example.edu"), person("b-2", "LI, Ming", "b", "two@example.edu")])) == 2


def test_site_urls_skips_aggregators_and_adds_scheme():
    assert site_urls("https://scholar.google.com/x https://a.example.org") == ["https://a.example.org"]
    assert site_urls("lab.example.org") == ["https://lab.example.org"]
    assert site_urls("") == []


def test_rank_links_puts_recruiting_first_and_stays_on_site():
    html = """<a href="/news">News</a><a href="/join">Join us</a>
              <a href="https://other.example/join">Elsewhere</a><a href="/cv.pdf">CV</a>"""
    assert rank_links(html, "https://lab.example.org/", 5) == [
        "https://lab.example.org/join", "https://lab.example.org/news"]
