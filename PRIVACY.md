# Privacy Policy — Theme Candidate Stock Comparison

**Effective date: August 2, 2026**

This Privacy Policy applies to the external Action service used by the **Theme Candidate Stock Comparison** Custom GPT (the “Service”). The Service is operated by the owner of this repository.

## 1. Scope

This policy covers data sent from ChatGPT to the Service through the configured GPT Action endpoints. It does not govern OpenAI’s own collection or use of information within ChatGPT. OpenAI’s processing is governed by OpenAI’s applicable terms and privacy policies.

The Service does not receive unrestricted access to a user’s ChatGPT account or conversation history. It receives only the structured data that ChatGPT sends when an Action is invoked.

## 2. Data the Service may receive

The Service may receive and process:

- investment themes, hypotheses, ticker symbols, issuer and listing metadata;
- evidence references, timestamps, source cutoffs, assumptions, judgments, scenario inputs, rankings, and phase outputs;
- generated session IDs, generation IDs, candidate-set IDs, and runtime status data;
- an API authentication credential in the HTTP Authorization header; and
- limited technical metadata that may be produced by hosting or network infrastructure, such as request time, request path, response status, and IP-related connection metadata.

The Service is not designed to collect names, addresses, payment details, government identifiers, health information, or other sensitive personal data. Users should not submit personal, confidential, regulated, or secret information through this GPT.

## 3. How data is used

Data is used only to:

- create and maintain comparison sessions;
- validate submitted phase artifacts against the runtime contracts;
- verify identity, chronology, evidence references, rankings, handoffs, and state integrity;
- persist and retrieve session state;
- return validated summaries, next-phase contracts, and handoff data;
- diagnose operational failures and protect the Service from unauthorized use.

The operator does not use Action data for advertising, marketing, user profiling, or model training.

## 4. Storage and retention

Session data is stored as JSON files in an operator-controlled Docker persistent volume. The Service does not use a separate user-account database.

Session data remains stored until the operator manually deletes the relevant session file, Docker volume, or backup. The current Service does not provide a user-facing automated deletion endpoint. Backups may exist when the operator creates them for recovery or migration and are retained until manually deleted.

## 5. Logging

The runtime is configured and operated so that Authorization headers and request bodies are not intentionally logged. Operational logs may contain limited metadata such as timestamps, endpoint paths, response codes, and error messages.

Authentication credentials are used only to authorize requests and are not written into session JSON files.

## 6. Sharing and service providers

The operator does not sell Action data and does not share it with advertisers.

Data may be processed in transit by infrastructure required to provide the Service, including:

- **OpenAI**, which operates ChatGPT and initiates Action requests; and
- **Cloudflare**, which may provide the HTTPS tunnel or network transport used to reach the private runtime.

Those providers process information under their own terms and privacy policies. GitHub hosts this repository and this Privacy Policy but is not used by the runtime to store comparison-session contents.

Data may also be disclosed when reasonably necessary to comply with law, protect the Service, investigate abuse, or prevent security harm.

## 7. Security

The Service uses measures including HTTPS transport, Bearer API-key authentication, loopback-bound container networking, restricted persistent-volume storage, atomic writes, schema validation, and integrity checks. No system can guarantee absolute security.

Users must not include API keys, passwords, private documents, or other secrets in prompts, phase artifacts, GitHub issues, or support requests.

## 8. Access, correction, and deletion requests

Requests concerning stored Action data may be submitted through the repository’s GitHub Issues page:

https://github.com/Hughey-T/Theme-Candidate-Stock-Comparison/issues

Include the relevant session ID when available, but do not post API keys, full request bodies, or confidential information in a public issue. The operator may request additional non-secret information to verify that a request relates to the identified session.

Because the Service generally stores structured investment-analysis data rather than account profiles, the operator may be unable to identify which person created a session without a valid session ID or equivalent technical identifier.

## 9. Children

The Service is not directed to children and is not intended to collect personal information from children.

## 10. International processing

OpenAI, Cloudflare, GitHub, and other infrastructure providers may process technical data in countries other than the user’s country of residence, subject to their respective terms and safeguards.

## 11. Changes to this policy

This policy may be updated when the Service, hosting arrangement, retention practice, or applicable requirements change. The effective date at the top of this document will be revised when material changes are made.

## 12. Financial-information disclaimer

The Service validates and stores structured stock-comparison artifacts. It does not provide investment advice, execute orders, guarantee source accuracy, or guarantee future investment performance.
