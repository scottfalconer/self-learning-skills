# Documentation rules

Use [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/) for this repository's English documentation.
Use Issue 9 as the source for writing rules and word meanings.

These rules apply to the README, skill instructions, reference files, CLI help, and generated documents.
Keep code identifiers, command options, paths, and quoted source text unchanged.
Keep the license text unchanged.

## Write and examine text

1. Use the STE dictionary to examine each word's meaning and part of speech.
2. Use the technical terms below when the dictionary does not contain a required software term.
3. Give each item one name throughout the documentation.
4. Write each procedure sentence as a command with one action.
5. Put a required condition before its instruction.
6. Keep procedure sentences at 20 words or fewer.
7. Keep descriptive sentences at 25 words or fewer.
8. Use active voice and simple verb forms.
9. Keep each paragraph on one subject, with no more than six sentences.
10. Remove idioms, contractions, decorative symbols, and unnecessary text.
11. Make sure that each command agrees with the CLI help.
12. Run each changed command example with temporary data.

Word counts alone do not establish STE conformance.
Examine the vocabulary, grammar, meaning, and technical terms together.
The official standard includes the full rules and dictionary.
This repository does not reproduce them.

## Technical terms

These terms describe this software. They do not change the meanings of words in the STE dictionary.

| Term | Meaning in this repository |
| --- | --- |
| agent | Software that uses a model and tools to do a task. |
| Aha Card | A stored result, with source data and conditions for use. |
| append-only | A file format in which an update adds a record and keeps earlier records. |
| backport | A change that puts selected knowledge into a skill's files. |
| backport bundle | Files that describe a proposed backport and its source records. |
| CLI | Command-line interface. |
| diff | A comparison that shows changes between two versions of a file. |
| frontmatter | The YAML block at the start of `SKILL.md`. |
| global store | A personal memory store that can serve more than one project. |
| JSONL | A text format with one JSON object on each line. |
| memory store | A directory that contains records for this skill. |
| payload | The JSON data supplied to a command. |
| permission | A rule that controls access to a file, command, or system. |
| project store | A memory store for one repository. |
| provenance | Data about the source and history of a record or change. |
| recommendation | A stored proposal for a future change. |
| repository | A directory whose files Git tracks. |
| scope | A field that identifies whether a result is applicable to one project or other projects. |
| signal | A record that shows the use or state of an Aha Card or recommendation. |
| skill | Agent instructions and their supporting files. |
| standard library | Python modules that come with Python. |
| symlink | A filesystem link to another path. |
| usage score | A number calculated from signals about a card. It does not measure correctness. |

Use `record`, `promote`, and `export-backport` as command names in code formatting.
In prose, write "record knowledge," "copy cards to the global store," and "create a backport bundle."

Use these technical verbs only for the specified computer processes.
Use an STE dictionary verb when it gives the same meaning.

| Verb | Computer process |
| --- | --- |
| apply | Use a patch or proposed change to update files. |
| append | Add data at the end of a file or list. |
| clone | Create a local copy of a Git repository. |
| deduplicate | Remove repeated records from a result. |
| export | Write selected records to another format or location. |
| filter | Select records that match given conditions. |
| initialize | Create the files and directories for a memory store. |
| redact | Replace private data with a marker before output or storage. |
| validate | Compare data with the required format and permitted values. |
