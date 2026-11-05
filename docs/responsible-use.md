# Using CivicLens responsibly

*[Versión en español](responsible-use.es.md)*

CivicLens helps citizens, journalists, oversight committees (veedurías) and public servants look
at public data. Its outputs are **starting points for questions**, not conclusions.

## 1. Flags are leads for review, not accusations
A "red flag" means a contract matches a pattern worth a second look (for example a single bidder,
an amount just under a threshold, or a supplier that is new and large). Each of these patterns has
legitimate explanations. A flag never proves wrongdoing, and the model can be wrong in both
directions: it misses cases and it flags normal ones.

## 2. Verify with the original source before publishing
Before you share, publish or report anything:
- open the contract in the original system (SECOP II, CanadaBuys, SEAO …) and read the documents;
- check that the amounts, dates and parties match;
- ask the entity for its explanation and include it;
- say which data you used, when you downloaded it, and what you cleaned.

## 3. Data is shown exactly as published
CivicLens does not correct, translate or complete the government's records. Names, amounts and
dates appear as the source published them, errors included. Cleaning steps you choose are listed
in the recipe, so anyone can repeat them. Amounts converted to another currency say so.

## 4. Models and averages describe groups, not people
Predictions, segments and fairness checks describe patterns in a table. Do not use them to judge
a specific person or company. Sensitive attributes (age, sex, marital status, nationality) are
never model inputs; they are only used to check whether results are fair across groups.

## 5. Personal data
Do not upload files with personal data you are not allowed to process. CivicLens warns when it
detects emails, phone numbers or ID numbers and offers to mask them. Uploaded files are deleted
after 24 hours.

Questions or a case where CivicLens misled you? [Give feedback](https://github.com/MariaAlejandraBoadaRodriguez/civiclens/issues/new?template=feedback.yml).
