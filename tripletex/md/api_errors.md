# API errors from submissions

# POST /ledger/voucher
response: "{"status":422,"code":18000,"message":"Validering feilet.","link":"https://tripletex.no/v2-docs/","developerMessage":null,"validationMessages":[{"field":"postings","message":"Kan ikke være null.","path":"null.postings","rootId":null}],"requestId":"6ffcc86a-9eea-4156-af2c-a861c665a226"}"

# POST /invoice
response: "{"status":422,"code":18000,"message":"Validering feilet.","link":"https://tripletex.no/v2-docs/","developerMessage":"VALIDATION_ERROR","validationMessages":[{"field":null,"message":"Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer.","path":null,"rootId":null}],"requestId":"ab8acfea-43e7-4e02-a555-e6e229ab4bff"}"

# POST /employee
response: "{"status":422,"code":18000,"message":"Validering feilet.","link":"https://tripletex.no/v2-docs/","developerMessage":"VALIDATION_ERROR","validationMessages":[{"field":"department.id","message":"Feltet må fylles ut.","path":null,"rootId":null}],"requestId":"70593c03-cb14-4ace-8153-24c373b8f5a0"}"
