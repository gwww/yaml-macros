"""
Entry point for parsing YAML and picking out the Python
'macros' for expanding.
"""

import io
import re
import textwrap
import yaml

from enum import Enum

LineType = Enum("LineType", "REGULAR COMMENT EVAL BLOCK IMPORT INCLUDE")


def yaml_macros_file(filename, reformat=True):
    """Convert macros in YAML file to pure YAML."""
    with open(filename) as stream:
        return _yaml_macros(stream, reformat)


def yaml_macros_string(yaml_str, reformat=True):
    """Convert macros in YAML string to pure YAML."""
    with io.StringIO(yaml_str) as stream:
        return _yaml_macros(stream, reformat)


def _yaml_macros(stream, reformat):
    processor = YAML_macros(stream)
    lines = processor.load()
    if reformat:
        return processor.dump()
    return lines


class YAML_macros:
    """Support 'macros' in YAML."""

    _re_exec_block_start = re.compile(r"^(.*)@@\s*$")
    _re_exec_block_end = re.compile(r"^\s*@@\s*$")
    _re_import = re.compile(r"^\s*@@((import|from)\s+.*?)(@@)?\s*$")
    _re_comment = re.compile(r"^\s*#")
    _re_include = re.compile(r"^(.*)@@include\s+(\S+?)(@@)?\s*$")
    _re_eval1 = re.compile(r"^(.*)@@(.+)@@(.*)")
    _re_eval2 = re.compile(r"^(.*)@@(.+)()")

    def __init__(self, stream):
        self._streams = [stream]
        self._macro_globals = {}
        self._parsers = [
            self._parse_comment,
            self._parse_exec_block,
            self._parse_import,
            self._parse_include,
            self._parse_eval,
        ]

    def load(self):
        self._lines = self._process_stream()
        return self._lines

    def dump(self):
        return yaml.dump(yaml.safe_load(self._lines))

    def _process_stream(self, indent_str=""):
        # print(f"_process_stream indent={len(indent_str)}")
        tokens = [self._parse_line(line) for line in self._streams[-1]]
        # for token in tokens:
        #     print(token)
        if indent_str:
            self._indent_tokens(tokens, indent_str)
        output = [self._process_line(token) for token in tokens]
        return "".join(output)

    def _process_line(self, token):
        line_type = token[0]
        if line_type == LineType.REGULAR:
            return token[1]
        if line_type == LineType.COMMENT:
            return token[2]
        if line_type == LineType.BLOCK:
            exec(textwrap.dedent(token[2]), self._macro_globals)
            return token[1]
        if line_type == LineType.EVAL:
            evaled = eval(token[2], self._macro_globals)
            if isinstance(evaled, str):
                if "\n" in evaled:
                    indent_string = "\n" + " " * len(token[1])
                    evaled = evaled.replace("\n", indent_string)
            else:
                evaled = evaled.__repr__()
            return f"{token[1]}{evaled}{token[3]}\n"
        if line_type == LineType.IMPORT:
            exec(token[2], self._macro_globals)
            return ""
        if line_type == LineType.INCLUDE:
            return self._process_include(token)

    def _process_include(self, token):
        indent_string = " " * len(token[1])
        filename = token[2]
        with open(filename) as stream:
            self._streams.append(stream)
            lines = self._process_stream(indent_string)
        return f"{token[1]}{lines}\n"

    def _indent_tokens(self, tokens, indent_str):
        first_line = True
        for idx, token in enumerate(tokens):
            if token[0] in [
                LineType.COMMENT,
                LineType.INCLUDE,
                LineType.COMMENT,
                LineType.BLOCK,
            ]:
                continue
            if first_line:
                first_line = False
                continue
            tokens[idx] = (token[0], indent_str + token[1], token[2], token[3])

    def _parse_line(self, line):
        for parser in self._parsers:
            parser_return_value = parser(line)
            if parser_return_value:
                return parser_return_value
        return (LineType.REGULAR, line, None, None)

    def _parse_exec_block(self, line):
        if line.count("@@") != 1:
            return None
        match = self._re_exec_block_start.match(line)
        if not match:
            return None

        return_text = match.group(1)
        block_lines = ""
        for line in self._streams[-1]:
            match = self._re_exec_block_end.match(line)
            if match:
                return (LineType.BLOCK, return_text, block_lines)
            else:
                block_lines += line

        # Error: block end not found before end of file
        return None

    def _parse_import(self, line):
        match = self._re_import.match(line)
        if not match:
            return None
        return (LineType.IMPORT, None, match.group(1))

    def _parse_comment(self, line):
        if self._re_comment.match(line):
            return (LineType.COMMENT, None, line)
        return None

    def _parse_include(self, line):
        match = self._re_include.match(line)
        if match:
            return (LineType.INCLUDE, match.group(1), match.group(2))
        return None

    def _parse_eval(self, line):
        match = self._re_eval1.match(line) or self._re_eval2.match(line)
        if not match:
            return None
        return (LineType.EVAL, match.group(1), match.group(2), match.group(3))
