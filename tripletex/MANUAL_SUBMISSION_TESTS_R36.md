# Manual Submission Tests — Round 36 (revision tripletex-00065-sxm)

Logs filter: `resource.labels.revision_name="tripletex-00065-sxm"`

Submit ONE at a time, wait for score, then submit next.

---

# SUBMISSION 1

## PROMPT
Vi har mottatt faktura INV-2026-9382 fra leverandøren Stormberg AS (org.nr 877462137) på 61600 kr inklusiv MVA. Beløpet gjelder kontortjenester (konto 6340). Registrer leverandørfakturaen med korrekt inngående MVA (25 %).

## SCORE
0/8

## NOTES
No API errors. But no points. Is /ledger the correct endpoints to use? Check the response and request bodys to see if data looks right. Research the tripletex api specs. Research /ledger and also other accounting terms for similar things.

---

# SUBMISSION 2

## PROMPT
Gjer forenkla årsoppgjer for 2025: 1) Rekn ut og bokfør årlege avskrivingar for tre eigedelar: Programvare (364700 kr, 4 år lineært, konto 1250), IT-utstyr (313300 kr, 8 år, konto 1210), Inventar (270900 kr, 6 år, konto 1240). Bruk konto 6010 for avskrivingskostnad og 1209 for akkumulerte avskrivingar. 2) Reverser forskotsbetalt kostnad (totalt 20500 kr på konto 1700). 3) Rekn ut og bokfør skattekostnad (22 % av skattbart resultat) på konto 8700/2920. Bokfør kvar avskriving som eit eige bilag.

## SCORE
TIMEOUT

## NOTES
A lot of validation steps (I thought this was removed), and then unresolved refs (I thought this was fixed)... And then a slow analyze response. We need to do research to figure out better ways to do math. I feel like there were some tips somewhere in the tripletex api specs. We need a better understanding of the API! Send in taxCode or something somewhere?

---

# SUBMISSION 3

## PROMPT
Gjer månavslutninga for mars 2026. Periodiser forskotsbetalt kostnad (14400 kr per månad frå konto 1710 til kostnadskonto). Bokfør månadleg avskriving for eit driftsmiddel med innkjøpskost 109500 kr og levetid 10 år (lineær avskriving til konto 6030). Kontroller at saldobalansen går i null. Bokfør også ei lønnsavsetjing (debet lønnskostnad konto 5000, kredit påløpt lønn konto 2900).


## SCORE
5/10

## NOTES
Okay, now I am certain! /ledger/account must be the wrong endpoint. It is returning fullResultSize: 0 for all the GET requests. I will say it again, we need to understand the tripletex API and accounting better!

---

# SUBMISSION 4

## PROMPT


## SCORE
/

## NOTES


---

# SUBMISSION 5

## PROMPT


## SCORE
/

## NOTES


---
