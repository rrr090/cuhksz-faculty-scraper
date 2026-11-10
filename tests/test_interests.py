import pytest

from cuhksz_faculty.interests import research_interests


def prof(fields, school="sse", areas=()):
    return {"research_field": list(fields), "academic_area": list(areas), "schools": [school]}


@pytest.mark.parametrize("fields, school, expected", [
    (["Deep Learning", "Stochastic Optimization"], "sds", ["Machine Learning", "Optimization and Operations Research",
                                                           "Probability and Stochastic Processes"]),
    (["Second Language Acquisition"], "hss", ["Linguistics and Translation"]),
    (["Collaborative Piano", "Piano"], "music", ["Piano and Keyboard"]),
    (["Urban green infrastructure"], "spp", ["Urban Studies and Geography", "Environment and Sustainability"]),
])
def test_fields_map_to_shared_interests(fields, school, expected):
    assert research_interests(prof(fields, school)) == expected


def test_official_areas_come_first_and_are_not_repeated():
    person = prof(["Machine Learning", "Robot Learning"], "sai", areas=["Machine Learning"])
    assert research_interests(person) == ["Machine Learning", "Robotics"]


@pytest.mark.parametrize("field, wrong", [
    ("Collaborative Learning Dynamics", "Economics"),        # "labor" inside "collaborative"
    ("Laboratory Animal Sciences", "Economics"),
    ("Medical Imaging", "Public Health"),                    # "aging" inside "imaging"
    ("high-energy physics/nuclear physics", "Energy"),
    ("Tumor microenvironment", "Environment and Sustainability"),
    ("next-generation solar cells", "Biological Sciences"),
    ("Evidence Synthesis", "Chemistry"),
    ("Drug-screening platform development", "Economics"),
])
def test_words_inside_other_words_do_not_match(field, wrong):
    assert wrong not in research_interests(prof([field]))


def test_school_specific_interests_stay_in_their_school():
    assert "Composition and Conducting" not in research_interests(prof(["Material composition"], "sse"))
