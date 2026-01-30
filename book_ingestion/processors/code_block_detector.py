"""Detects code blocks and terminal output in text"""

import re
from typing import List, Tuple


class CodeBlockDetector:
    """
    Identifies regions of text that are likely code or terminal output.
    Used to exclude these regions from chapter pattern matching.
    """

    def __init__(self):
        # Patterns that indicate a line is code
        self.code_indicators = [
            re.compile(r'^\s*[$#>]{1,2}\s+\w'),  # Shell prompts: $ cmd, # cmd, > cmd
            re.compile(r'^\s*>>>\s'),  # Python REPL
            re.compile(r'^\s{4,}\S'),  # Indented code (4+ spaces)
            re.compile(r'^\t+\S'),  # Tab-indented code
            re.compile(r'^\d+\s+\w+\s+\d+\s+\d+\s+[\d.]+'),  # ps/top output
            re.compile(r'^[│├└─┌┐┘┬┴┼]+'),  # Box drawing chars (tree output)
            re.compile(r'^\s*\|.*\|.*\|'),  # Pipe-delimited tables
            re.compile(r'^[\w./]+:\d+:'),  # File:line: (grep output)
            re.compile(r'^\s*(?:def|class|import|from|if|for|while|return|async|await)\s'),  # Python keywords at start
            re.compile(r'^\s*(?:function|const|let|var|import|export|if|for|while|return)\s'),  # JS keywords
        ]

        # Minimum consecutive code lines to form a block
        self.min_block_size = 2

    def detect(self, text: str) -> List[Tuple[int, int]]:
        """
        Detect code block regions in text.

        Returns:
            List of (start_line, end_line) tuples (0-indexed, inclusive)
        """
        lines = text.split('\n')
        code_line_indices = []

        for i, line in enumerate(lines):
            if self.is_code_line(line):
                code_line_indices.append(i)

        # Merge consecutive or near-consecutive code lines into blocks
        return self._merge_into_blocks(code_line_indices, len(lines))

    def is_code_line(self, line: str) -> bool:
        """Check if a single line looks like code"""
        # Empty lines are not code by themselves
        if not line.strip():
            return False

        # Check against code indicators
        for pattern in self.code_indicators:
            if pattern.match(line):
                return True

        # Heuristic: high density of special characters
        if self._has_code_char_density(line):
            return True

        return False

    def _has_code_char_density(self, line: str) -> bool:
        """Check if line has high density of code-like characters"""
        if len(line.strip()) < 10:
            return False

        code_chars = set('()[]{}=<>|&;:\'\"\\/@#$%^*+-')
        char_count = sum(1 for c in line if c in code_chars)
        density = char_count / len(line.strip())

        # Also check for multiple numbers separated by spaces (like ps output)
        number_groups = re.findall(r'\b\d+\b', line)
        if len(number_groups) >= 4:
            return True

        return density > 0.15

    def _merge_into_blocks(self, indices: List[int], total_lines: int) -> List[Tuple[int, int]]:
        """Merge nearby code line indices into contiguous blocks"""
        if not indices:
            return []

        blocks = []
        block_start = indices[0]
        block_end = indices[0]

        for idx in indices[1:]:
            # Allow gap of 1 line (e.g., blank line between code)
            if idx <= block_end + 2:
                block_end = idx
            else:
                # Save current block if it meets minimum size
                if block_end - block_start + 1 >= self.min_block_size:
                    blocks.append((block_start, block_end))
                block_start = idx
                block_end = idx

        # Don't forget the last block
        if block_end - block_start + 1 >= self.min_block_size:
            blocks.append((block_start, block_end))

        return blocks

    def get_non_code_lines(self, text: str) -> List[int]:
        """Get indices of lines that are NOT in code blocks"""
        lines = text.split('\n')
        code_regions = self.detect(text)

        code_lines = set()
        for start, end in code_regions:
            code_lines.update(range(start, end + 1))

        return [i for i in range(len(lines)) if i not in code_lines]
