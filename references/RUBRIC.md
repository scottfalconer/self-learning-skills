# Capture criteria

Record a result when it can help a later task. A useful card states a problem, a tested solution, and the conditions for use.

## Select a result

Prefer results that required investigation. Examples include:

- A data format with required fields and known limits
- A command sequence that solved a repeatable failure
- An interface condition that a caller must satisfy
- A failed method and the conditions that caused its failure
- A shorter procedure with the same observed result

Keep the card small enough to use without reading a full transcript. If no result meets these criteria, do not create a card.

## Record source data

Identify the source that supports the result. Use a file reference, documentation link, exact command, or observed test result.

Distinguish observations from assumptions. For example, one successful response does not prove that all requests succeed. One `403` response does not identify every possible cause of access failure.

Keep conditions that can change the result. These conditions can include a software version, account permissions, environment, or input format.

## Describe the action

Give the reader enough information to repeat the procedure. Use commands, field names, or a short sequence of steps.

Do not replace a clear procedure with general advice. For example, "be careful with dates" does not identify an action. "Parse the timestamp as UTC before conversion" identifies an action and a condition.

## Select scope

Use `project` when the result depends on this repository. Use `portable` when the result is applicable to other projects.

To prepare portable content, replace project values with placeholders. Keep the technical conditions that affect correctness. Refer to [portability](PORTABILITY.md) before you copy a card elsewhere.

## Keep private data out

Do not store credentials, personal data, or private payloads. Use field names, types, and synthetic examples when actual values are unnecessary.

Automatic redaction can miss secrets. `shareable: false` is a content classification, not access control.

## Avoid duplicate records

Search for an existing card before you add the same result again. Add new source data when it changes the card's value. Record actual use with a signal.

Do not add signals only to increase a score. Do not convert a repeated assumption into a fact.

## Separate results from proposals

An Aha Card records a result. A recommendation proposes a change.

State the expected benefit as an estimate until measurements support it. Do not report an untested proposal as a completed improvement.
