"""Crafted corpus for the examiner's targeted stage-4 probes (written from the spec only).

usage: python3 gen_corpus.py <out dir>
Every company keeps at most 10 searchable pages per epoch (the mock returns at most 10 results).
"""
import json
import os
import sys
from urllib.parse import urlsplit

COMPANIES = {}


def host(url):
    return urlsplit(url).hostname


def page(company, url, text, *, kind="news", epochs=(0,), registrant=None, canonical=None, fpb=None,
         tf=None, published=None, searchable=True):
    entry = {"url": url, "kind": kind, "epochs": list(epochs), "published_at": published, "true_from": tf,
             "title": f"{company} | {host(url)}", "text": text, "facts": {}, "searchable": searchable,
             "lineage": {"canonical": canonical, "first_published_by": fpb,
                         "registrant": registrant or host(url)}}
    COMPANIES[company]["pages"].append(entry)


def company(domain, name):
    COMPANIES[domain] = {"domain": domain, "names": [name], "pages": [], "research": {}}
    return domain


# ---- acme-robotics.test: the ceo's corroboration over time ------------------------------------------------
A = company("acme-robotics.test", "Acme Robotics")
page(A, "https://acme-robotics.test/about", "Acme Robotics CEO: Dana Ruiz.", kind="own", epochs=(0, 1, 2))
page(A, "https://acme-robotics.test/about", "Acme Robotics CEO: Sam Ortiz.", kind="own", epochs=(3, 4))
page(A, "https://acme-robotics.test/about", "Acme Robotics CEO: Dana Ruiz.", kind="own", epochs=(5,))
page(A, "https://newsa.test/acme", "Acme Robotics CEO: Dana Ruiz.", epochs=(1,), published="2025-01-01T00:00:00Z")
page(A, "https://newsb.test/acme", "Acme Robotics CEO: Sam Ortiz.", epochs=(4,), published="2025-01-02T00:00:00Z")

# ---- foundry-labs.test: executives members ----------------------------------------------------------------
F = company("foundry-labs.test", "Foundry Labs")
page(F, "https://foundry-labs.test/team", "Foundry Labs CFO: Ana Silva.\nFoundry Labs COO: Ben Okafor.",
     kind="own", epochs=(0, 1))
page(F, "https://foundry-labs.test/team", "Foundry Labs CFO: Ana Silva.\nFoundry Labs COO: Cara Diaz.",
     kind="own", epochs=(2,))
page(F, "https://newsc.test/foundry", "Foundry Labs CFO: Ana Silva.", epochs=(0, 1, 2))
page(F, "https://newsd.test/foundry", "Foundry Labs COO: Ben Okafor.", epochs=(1,))

# ---- harbor-tech.test: investors over time (typing, extraction rules, /values) -----------------------------
H = company("harbor-tech.test", "Harbor Tech")
page(H, "https://harbor-tech.test/investors", "Harbor Tech investors include Bluebird Capital and Northwind Ventures.",
     kind="own", epochs=(0, 1, 2), tf="2024-05-02")
page(H, "https://harbor-tech.test/investors", "Harbor Tech investors include Bluebird Capital.",
     kind="own", epochs=(3, 4), tf="2024-05-02")
page(H, "https://harbor-tech.test/funding", "Greyfriars Holdings participated in a round for Harbor Tech.",
     kind="own", epochs=(1, 2, 3, 4), tf="2023-01-01")
page(H, "https://harbor-tech.test/rounds", "Redwood Partners participated in the Harbor Tech round.",
     kind="own", epochs=(2, 3, 4), tf="2025-02-02")
page(H, "https://harbor-tech.test/backers", "Harbor Tech investors include Zenith Fund.",
     kind="own", epochs=(4,), tf=None)
page(H, "https://harbor-tech.test/series", "Harbor Tech raised $40M in a round led by General Atlantic.",
     kind="own", epochs=(0, 1, 2, 3, 4), tf="2022-01-01")
page(H, "https://harbor-tech.test/leadership", "Harbor Tech is led by Dana Ruiz.", kind="own", epochs=(0, 1, 2, 3, 4))
page(H, "https://harbor-tech.test/capital", "Harbor Tech Capital participated in the round.",
     kind="own", epochs=(0, 1, 2, 3, 4))
page(H, "https://harbor-tech.test/press", "Sequoia participated in the Harbor Tech round.",
     kind="own", epochs=(0, 1, 2, 3, 4))
page(H, "https://harbor-tech.test/rumours", "Harbor Tech reportedly raised $5M led by Phantom Capital.",
     kind="own", epochs=(0, 1, 2, 3, 4))

# ---- ledger-works.test: investor name runs, membership by kind/origins, lookalikes ------------------------
L = company("ledger-works.test", "Ledger Works")
page(L, "https://ledger-works.test/a", "Ledger Works is backed by Solo Partners.", kind="own")
page(L, "https://ledger-works.test/b", "Ledger Works investors include Acme Widget Fund Holdings.", kind="own")
page(L, "https://ledger-works.test/c", "Ledger Works raised $10M, backed by Sequoia.", kind="own")
page(L, "https://newsx.test/lw", "Ledger Works investors include Quartz Capital.")
page(L, "https://newsy.test/lw", "Ledger Works investors include Quartz Capital.")
page(L, "https://ledger-works-group.test/about",
     "Ledger Works investors include Mirage Capital.\nLedger Works investors include Ghost Capital.",
     kind="own", registrant="parked.test")
page(L, "https://daily.test/lw", "Ledger Works investors include Mirage Capital.")
page(L, "https://daily3.test/lw", "Ledger Works investors include Lone Ventures.")

# ---- copy-desk.test: lineage, canonical chains, originals --------------------------------------------------
C = company("copy-desk.test", "Copy Desk")
SYN = "Copy Desk investors include Syndic Capital."
page(C, "https://daily-a.test/cd1", SYN, canonical="https://pressroom.test/cd")
page(C, "https://daily-b.test/cd2", SYN, canonical="https://pressroom.test/cd")
page(C, "https://pressroom.test/cd", SYN, searchable=False)
page(C, "https://chain1.test/p", "Copy Desk investors include Chain Capital.", registrant="reg1.test",
     canonical="https://chain2.test/p")
page(C, "https://chain2.test/p", "Copy Desk investors include Chain Capital.", searchable=False,
     canonical="https://chain3.test/p")
page(C, "https://chain3.test/p", "Copy Desk investors include Chain Capital.", searchable=False,
     canonical="https://chain4.test/p")
page(C, "https://chain4.test/p", "Copy Desk investors include Chain Capital.", searchable=False,
     canonical="https://chain5.test/p")
page(C, "https://chain5.test/p", "Copy Desk investors include Chain Capital.", searchable=False,
     registrant="reg5.test")
page(C, "https://hop1.test/p", "Copy Desk investors include Hop Capital.", canonical="https://hop2.test/p")
page(C, "https://hop2.test/p", "Copy Desk investors include Hop Capital.", searchable=False,
     canonical="https://hop3.test/p")
page(C, "https://hop3.test/p", "Copy Desk investors include Hop Capital.", searchable=False,
     canonical="https://hop4.test/p")
page(C, "https://hop4.test/p", "Copy Desk investors include Hop Capital.", searchable=False,
     registrant="reghop4.test")
page(C, "https://void.test/p", "Copy Desk investors include Void Capital.", canonical="https://nowhere.test/zz")
page(C, "https://selfcopy.test/s", "Copy Desk investors include Self Capital.", registrant="selfreg.test",
     canonical="https://selfcopy.test/s")
page(C, "https://cyc-x.test/1", "Copy Desk investors include Cycle Capital.", registrant="cycreg.test",
     canonical="https://cyc-y.test/2")
page(C, "https://cyc-y.test/2", "Copy Desk investors include Cycle Capital.", searchable=False,
     canonical="https://cyc-x.test/1")
page(C, "https://mirror.test/f", "Copy Desk investors include Wire Capital.", fpb="Wire.Test",
     canonical="https://other.test/o")
page(C, "https://mirror2.test/f", "Copy Desk investors include Wire Capital.", fpb="wire.test")

if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for domain, data in COMPANIES.items():
        with open(os.path.join(out, f"{domain}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    with open(os.path.join(out, "key.json"), "w", encoding="utf-8") as fh:
        json.dump({}, fh)
