# wordstat

A tiny word-frequency command-line tool. No dependencies: plain Node.js 24 built-ins only.

## Usage

    node bin/tool.js [--upper] [--limit N] <file>

`<file>` is the path (relative to the current working directory, or absolute) of a UTF-8 text file.
The two options are independent and optional and may be given in either order; the file path comes last.

- `--limit N`  how many entries to put in `top`. N is a positive integer. Default: 3.
- `--upper`    print the words inside `top` in upper case (see rule 5 below).

## Output

On success the tool prints exactly one line to stdout: the compact `JSON.stringify` form of an object with
the keys `lines`, `words`, `top` in that order, followed by a single newline. It then exits with code 0.
Example of the shape:

    {"lines":2,"words":7,"top":[["the",3],["cat",2],["sat",1]]}

## Counting rules

1. `lines` is the number of `\n` characters in the file, plus 1 if the file is non-empty and its last
   character is not `\n`. An empty file has 0 lines. (So `a\nb\n` and `a\nb` both have 2 lines.)
2. Tokenising: lower-case the whole text with `toLowerCase()`, then the tokens are the matches of the
   regular expression `/[a-z0-9']+/g`. Everything else (whitespace, punctuation, hyphens, any other
   character) separates tokens. `Don't` is one token (`don't`); `well-known` is two (`well`, `known`);
   `2024` is a token.
3. `words` is the total number of tokens.
4. `top` is a list of `[word, count]` pairs: the N most frequent distinct tokens, ordered by count
   descending. Tokens with the same count are ordered alphabetically ascending, that is by plain string
   comparison of the lower-cased token (`a < b`). If there are fewer than N distinct tokens, list them all.
5. `--upper` changes only how the words in `top` are printed: each one is converted with `toUpperCase()`.
   Counting, ordering and tie-breaking still happen on the lower-cased tokens; `lines` and `words` are
   unchanged.

## Errors

If `<file>` does not exist: print exactly the line `error: file not found` to stderr, print nothing to
stdout, and exit with code 2.
