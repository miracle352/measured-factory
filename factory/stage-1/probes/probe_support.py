#!/usr/bin/env python3
"""Spec-only probes of stage-1/support.py. Usage: python3 -I probe_support.py <path-to-stage-1-dir>
Expected values derive from Appendix A text only. Prints FAIL lines with the spec rule."""
import sys, importlib.util
d = sys.argv[1]
spec = importlib.util.spec_from_file_location("support", d + "/support.py")
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
D = "acme-robotics.test"
fails = 0; n = 0


def chk(cond, ref, msg):
    global fails, n
    n += 1
    if not cond:
        fails += 1; print("FAIL", ref, msg)


def sup(f, v, ex, want, ref, dom=D):
    try: got = S.supports(f, v, ex, dom)
    except Exception as e: got = repr(e)
    chk(got == want, ref, f"supports({f!r},{v!r},{ex!r}) want {want} got {got}")


def sent(t, want, ref):
    try: got = S.sentences(t)
    except Exception as e: got = repr(e)
    chk(got == want, ref, f"sentences({t!r}) want {want} got {got}")


# --- A.1 sentences
sent("One. Two.", ["One.", "Two."], "A.1")
sent("One.Two", ["One.Two"], "A.1 no whitespace")
sent("A\nB", ["A", "B"], "A.1 line break")
sent('He said "stop." Then left.', ['He said "stop."', "Then left."], "A.1 quote after dot")
sent("Really?” Yes.", ["Really?”", "Yes."], "A.1 ” after ?")
sent("It ended.) Next", ["It ended.)", "Next"], "A.1 ) after dot")
sent("What?! Yes", ["What?!", "Yes"], "A.1 ?!")
sent("Wait... Then", ["Wait...", "Then"], "A.1 ellipsis")
sent("The legal name is Acme Robotics, Inc. It is based in Lisbon.", ["The legal name is Acme Robotics, Inc. It is based in Lisbon."], "A.1 suffix dot does not end")
sent("Founded by Dr. Smith.", ["Founded by Dr.", "Smith."], "A.1 non-suffix abbreviation")
sent("ABCorp. Next", ["ABCorp.", "Next"], "A.1 suffix as whole word only")
sent("Acme L.P. Next. Then", ["Acme L.P. Next.", "Then"], "A.1 L.P.")
sent("Acme s.r.o. Next", ["Acme s.r.o. Next"], "A.1 s.r.o.")
sent("Acme S.p.A. Next", ["Acme S.p.A. Next"], "A.1 S.p.A.")
sent("Acme Ltd. Next", ["Acme Ltd.", "Next"], "A.1 Ltd is listed without a dot: its dot ends the sentence")
sent("Acme Corp.\nNext", ["Acme Corp.", "Next"], "A.1 line")
sent("  Hello.   World  ", ["Hello.", "World"], "A.1 trim")
sent("Hi.\n\n  \nBye", ["Hi.", "Bye"], "A.1 empty dropped")
sent("Where? Here! There.", ["Where?", "Here!", "There."], "A.1")
sent("It is 3.5 m. Next", ["It is 3.5 m.", "Next"], "A.1 decimal")
sent("U.S. army", ["U.S.", "army"], "A.1 S. is not a suffix")
sent("Acme B.V. Next", ["Acme B.V. Next"], "A.1 B.V.")
# --- header
h, p = S.split_header("Kind: news\nFirst-Published-By: wire.test\nFacts: {\"ceo\": \"X Y\"}\n\nBody one.\nBody two.")
chk(len(h) == 3 and p == "Body one.\nBody two.", "§4 pages", f"split_header basic {h!r} {p!r}")
h, p = S.split_header("Hello world\nKind: news\n\nx")
chk(h == [] and p == "Hello world\nKind: news\n\nx", "§4 pages", f"no header when first line not header: {h!r} {p!r}")
h, p = S.split_header("kind: news\n\nbody")
chk(h == [] and p == "kind: news\n\nbody", "§4 pages", f"lowercase name is not a header: {h!r} {p!r}")
h, p = S.split_header("Kind: news\n\nAcme Robotics CEO: Sam Ortiz.")
chk(p == "Acme Robotics CEO: Sam Ortiz." and len(h) == 1, "§4 pages", f"{h!r} {p!r}")
h, p = S.split_header("Kind: news\nPublished: 2026-01-01T00:00:00Z")
chk(p == "" and len(h) == 2, "§4 pages", f"header only {h!r} {p!r}")
# --- spec examples
sup("ceo", "Dana Ruiz", "Dana Ruiz has led Acme Robotics as chief executive since 2021.", True, "A.2 ex")
sup("ceo", "Sam Ortiz", "Acme Robotics CEO: Sam Ortiz.", True, "A.2 ex")
sup("founded_year", 2014, "Acme Robotics was founded in 2014.", True, "A.2 ex")
sup("headcount_range", "51-200", "Acme Robotics employs about 120 people.", True, "A.2 ex")
sup("funding_total", 40000000, "Acme Robotics is reportedly in talks to raise $40M.", False, "A.2 ex negation")
sup("hq_city", "Porto", "Acme Robotics opened a sales office in Porto.", False, "A.2 ex")
# --- name / whole word / case
sup("founded_year", 2014, "ACME ROBOTICS was FOUNDED in 2014.", True, "A.2 case-insens")
sup("founded_year", 2014, "acme-robotics.test was founded in 2014.", True, "A.2 domain")
sup("founded_year", 2014, "Acme Robotic was founded in 2014.", False, "A.2 name required")
sup("founded_year", 2014, "NotAcme Robotics was founded in 2014.", False, "A.2 whole word before")
sup("founded_year", 2014, "Acme Roboticsx was founded in 2014.", False, "A.2 whole word after")
sup("founded_year", 2014, "Acme Robotics was refounded in 2014.", False, "A.2 phrase whole word")
sup("founded_year", 2014, "Other Co was founded in 2014.", False, "A.2 no company")
sup("founded_year", 2014, "xacme-robotics.test was founded in 2014.", False, "A.2 domain whole word")
sup("founded_year", 2014, "Acme Robotics was founded in 2014. It grew.", False, "A.2.1 single sentence")
sup("founded_year", 2014, "Acme Robotics was founded in 2014, not 2015.", False, "A.3 not")
sup("founded_year", 2014, "Acme Robotics was founded in 2014 (knotted).", True, "A.3 'not' whole word")
sup("founded_year", 2014, "Acme Robotics could be founded in 2014.", False, "A.3 could")
sup("founded_year", 2014, "Acme Robotics was formerly founded in 2014.", False, "A.3 formerly")
sup("ceo", "Sam Ortiz", "The former CEO of Acme Robotics is Sam Ortiz.", False, "A.3 former")
sup("founded_year", 2014, "Acme Robotics was established in 2014.", True, "A.3 established")
sup("founded_year", 2014, "Acme Robotics was incorporated in 2014.", True, "A.3 incorporated")
sup("founded_year", 2014, "Acme Robotics' founding year is 2014.", True, "A.3 founding")
# --- founded_year formats
sup("founded_year", 1800, "Acme Robotics was founded in 1800.", True, "A.4 1800")
sup("founded_year", 2099, "Acme Robotics was founded in 2099.", True, "A.4 2099")
sup("founded_year", 1799, "Acme Robotics was founded in 1799.", False, "A.4 1799")
sup("founded_year", 2100, "Acme Robotics was founded in 2100.", False, "A.4 2100")
sup("founded_year", 2014, "Acme Robotics was founded in 2014 and 2015.", False, "A.2.5 all values")
sup("founded_year", 2014, "Acme Robotics was founded in 2014-2015.", False, "A.2.5 two years")
sup("founded_year", 2014, "Acme Robotics was founded in 2014 and raised $12M.", True, "A.4 only years")
sup("founded_year", 1999, "Acme Robotics was founded in 1999 and raised 2014 dollars.", True, "A.4 not part of amount")
sup("founded_year", 1999, "Acme Robotics was founded in 1999 and raised $2014.", True, "A.4 not part of amount $")
sup("founded_year", 2014, "Acme Robotics was founded in 2014a.", False, "A.4 digits next to letter")
sup("founded_year", 2014, "Acme Robotics was founded in a2014.", False, "A.4 digits next to letter")
sup("founded_year", 2014, "Acme Robotics was founded in 20,14.", False, "A.4 bad number")
sup("founded_year", 2014, "Acme Robotics was founded in 1,2014.", False, "A.4 bad number")
sup("founded_year", 2014, "Acme Robotics was founded in 2014.5.", False, "A.4 joined by . to digits")
# --- headcount
for ex, v, w in [
    ("Acme Robotics has 51-200 employees.", "51-200", True),
    ("Acme Robotics has 40-60 employees.", "51-200", False),
    ("Acme Robotics has 120-150 employees.", "51-200", True),
    ("Acme Robotics has 10-11 employees.", "1-10", False),
    ("Acme Robotics has 1,200 employees.", "1001-5000", True),
    ("Acme Robotics has 1,20 employees.", "1001-5000", False),
    ("Acme Robotics has 12.5 employees.", "11-50", False),
    ("Acme Robotics has 0 employees.", "1-10", False),
    ("Acme Robotics has 1 employees.", "1-10", True),
    ("Acme Robotics has 10 employees.", "1-10", True),
    ("Acme Robotics has 11 employees.", "11-50", True),
    ("Acme Robotics has 50 employees.", "11-50", True),
    ("Acme Robotics has 201 employees.", "201-500", True),
    ("Acme Robotics has 1000 employees.", "501-1000", True),
    ("Acme Robotics has 5001 employees.", "5001-10000", True),
    ("Acme Robotics has 10000 employees.", "5001-10000", True),
    ("Acme Robotics has 10001 employees.", "10001+", True),
    ("Acme Robotics has 10001+ employees.", "10001+", True),
    ("Acme Robotics has 5k employees.", "1001-5000", False),
    ("Acme Robotics employs roughly 120 people.", "51-200", True),
    ("Acme Robotics employs 120, people.", "51-200", True),
    ("Acme Robotics employs 120.5 people.", "51-200", False),
    ("Acme Robotics employs 120 people and raised $12M.", "51-200", True),
    ("Acme Robotics employs 120 people and was founded in 2014.", "51-200", False),
    ("Acme Robotics employs 120 people across 3 offices.", "51-200", False),
    ("Acme Robotics workforce: 120.", "51-200", True),
]:
    sup("headcount_range", v, ex, w, "A.4/A.5 headcount")
# --- funding
for ex, v, w in [
    ("Acme Robotics raised $12M.", 12000000, True),
    ("Acme Robotics raised $12m.", 12000000, True),
    ("Acme Robotics raised $12mn.", 12000000, True),
    ("Acme Robotics raised $12MN.", 12000000, True),
    ("Acme Robotics raised $1.5bn.", 1500000000, True),
    ("Acme Robotics raised $12k.", 12000, True),
    ("Acme Robotics raised $12 thousand.", 12000, True),
    ("Acme Robotics raised $12.5 million.", 12500000, True),
    ("Acme Robotics raised $12.5 Billion.", 12500000000, True),
    ("Acme Robotics raised US$12 million.", 12000000, True),
    ("Acme Robotics raised us$12 million.", 12000000, True),
    ("Acme Robotics raised USD 12 million.", 12000000, True),
    ("Acme Robotics raised USD12 million.", 12000000, True),
    ("Acme Robotics raised $12,000,000.", 12000000, True),
    ("Acme Robotics raised $12,00.", 1200, False),
    ("Acme Robotics raised 12 million dollars.", 12000000, True),
    ("Acme Robotics raised 12,000,000 US dollars.", 12000000, True),
    ("Acme Robotics raised 12 Million US Dollars.", 12000000, True),
    ("Acme Robotics raised 12 dollars.", 12, True),
    ("Acme Robotics raised $12 M.", 12, True),
    ("Acme Robotics raised $12 M.", 12000000, False),
    ("Acme Robotics raised $12Mx.", 12000000, False),
    ("Acme Robotics raised A$12M.", 12000000, False),
    ("Acme Robotics raised €12 million.", 12000000, False),
    ("Acme Robotics raised 12 million euros.", 12000000, False),
    ("Acme Robotics raised $12M and $12 million.", 12000000, True),
    ("Acme Robotics raised $12M and $13M.", 12000000, False),
    ("Acme Robotics raised $12.0000001 million.", 12000000, False),
    ("Acme Robotics raised $0.0005 million.", 500, True),
    ("Acme Robotics raised $.5M.", 500000, False),
    ("Acme Robotics raised $12M in 2014.", 12000000, True),
    ("Acme Robotics raised $1.2.3M.", 1200000, False),
    ("Acme Robotics raised $12 millions.", 12, True),
    ("Acme Robotics raised $12M.", 12, False),
]:
    sup("funding_total", v, ex, w, "A.4/A.5 funding")
# --- hq_city
for ex, v, w in [
    ("Acme Robotics is headquartered in Lisbon.", "Lisbon", True),
    ("Acme Robotics is headquartered in Lisbon, Portugal.", "Lisbon", True),
    ("Acme Robotics is based in New York City.", "New York City", True),
    ("Acme Robotics is based in New York City.", "New York", False),
    ("Acme Robotics is based in lisbon.", "lisbon", False),
    ("Acme Robotics is based in LISBON.", "LISBON", False),
    ("Acme Robotics is based in Saint-Étienne.", "Saint-Étienne", True),
    ("Acme Robotics is based in Zürich.", "Zürich", True),
    ("Acme Robotics is based in Lisbon and Porto.", "Lisbon", True),
    ("Acme Robotics is headquartered in Lisbon and based in Porto.", "Lisbon", False),
    ("Acme Robotics has its head office in Berlin.", "Berlin", True),
    ("Acme Robotics has its registered office in Berlin.", "Berlin", True),
    ("Acme Robotics is not based in Lisbon.", "Lisbon", False),
    ("Acme Robotics has headquarters in Lisbon.", "Lisbon", True),
    ("Acme Robotics is based in Lisbon Portugal.", "Lisbon Portugal", True),
    ("Acme Robotics is based in Lisbon-Sul.", "Lisbon-Sul", True),
    ("Acme Robotics is based in L.", "L", False),
    ("Acme Robotics is based in the Lisbon.", "Lisbon", False),
]:
    sup("hq_city", v, ex, w, "A.4 hq_city")
# --- ceo
for ex, v, w in [
    ("Dana Ruiz is CEO of Acme Robotics.", "Dana Ruiz", True),
    ("Acme Robotics chief executive officer Dana Ruiz.", "Dana Ruiz", True),
    ("Acme Robotics CEO Dana Marie Ruiz.", "Dana Marie Ruiz", True),
    ("Acme Robotics CEO Dana Marie Ruiz Smith.", "Dana Marie Ruiz Smith", False),
    ("Acme Robotics CEO Dana Marie Ruiz Smith.", "Dana Marie Ruiz", False),
    ("Dana Ruiz and Sam Ortiz lead Acme Robotics as CEO.", "Dana Ruiz", False),
    ("Founder Dana Ruiz is CEO of Acme Robotics.", "Founder Dana Ruiz", True),
    ("Founder Dana Ruiz is CEO of Acme Robotics.", "Dana Ruiz", False),
    ("Acme Robotics Dana Ruiz CEO.", "Dana Ruiz", True),
    ("Acme Robotics CEO Dana.", "Dana", False),
    ("Acme Robotics CEO dana ruiz.", "dana ruiz", False),
    ("Acme Robotics CEO Dana Müller.", "Dana Müller", True),
    ("Acme Robotics CEO Dana RUIZ.", "Dana RUIZ", False),
    ("Acme Robotics CEO Dana Ruiz-Lopez.", "Dana Ruiz", True),
    ("Acme Robotics CEO Dana Ruiz, Sam Ortiz.", "Dana Ruiz", False),
]:
    sup("ceo", v, ex, w, "A.4 ceo")
# --- legal_name (suffix mandatory, the comma before it optional)
for ex, v, w in [
    ("The registered name is Acme Robotics, Inc.", "Acme Robotics, Inc.", True),
    ("The registered name is Acme Robotics Inc.", "Acme Robotics Inc.", True),
    ("The legal entity is Acme Robotics Holdings GmbH.", "Acme Robotics Holdings GmbH", True),
    ("Acme Robotics Ltd is the legal entity.", "Acme Robotics Ltd", True),
    ("Acme Robotics Ltdx is the legal entity.", "Acme Robotics Ltdx", False),
    ("The legal name is Acme Robotics.", "Acme Robotics", False),
    ("Acme Robotics, Inc. and Acme Robotics Corp. is the legal entity.", "Acme Robotics, Inc.", False),
    ("Acme Robotics S.p.A. is the legal entity.", "Acme Robotics S.p.A.", True),
    ("Acme Robotics AI Labs GmbH is the legal entity.", "Acme Robotics AI Labs GmbH", True),
    ("Acme Robotics Ab is the legal entity.", "Acme Robotics Ab", False),
    ("Acme Robotics AB is the legal entity.", "Acme Robotics AB", True),
    ("Acme Robotics Pty Ltd is the legal entity.", "Acme Robotics Pty Ltd", True),
    ("Registered as acme-robotics.test Ltd.", "acme-robotics.test Ltd", True),
    ("Acme Robotics, Inc., the legal entity.", "Acme Robotics, Inc.", True),
    ("Acme Robotics A/S is the legal entity.", "Acme Robotics A/S", True),
    ("Acme Robotics plc is the legal entity.", "Acme Robotics plc", True),
    ("Acme Robotics Plc is the legal entity.", "Acme Robotics Plc", False),
    ("Acme Robotics s.r.o. is the legal entity.", "Acme Robotics s.r.o.", True),
    ("Acme Robotics Group Inc. is the legal entity.", "Acme Robotics Group Inc.", True),
]:
    sup("legal_name", v, ex, w, "A.4 legal_name")
# --- extract_values spot checks
try:
    chk(sorted(S.extract_values("founded_year", "Acme Robotics was founded in 2014 and 2015.", D)) == [2014, 2015], "A.4", "extract_values founded two years")
    chk(S.extract_values("funding_total", "Acme Robotics raised $12M.", D) == [12000000], "A.5", "extract_values funding")
    chk(S.extract_values("hq_city", "Acme Robotics opened an office in Porto.", D) == [], "A.4", "extract_values hq none")
except Exception as e:
    chk(False, "api", f"extract_values raised {e!r}")
print(f"{n} checks, {fails} failed")
sys.exit(1 if fails else 0)
