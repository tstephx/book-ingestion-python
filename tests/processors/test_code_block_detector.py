"""Tests for code block detection"""

import pytest
from src.processors.code_block_detector import CodeBlockDetector


class TestCodeBlockDetector:
    def setup_method(self):
        self.detector = CodeBlockDetector()

    def test_detects_terminal_output_with_numbers(self):
        """Lines like '10432 chris 20 0 471m' should be detected as code"""
        text = """Chapter 3 Using the Shell

This chapter covers shell basics.

$ ps aux
10432 chris 20 0 471m 121m 18m S 99.9 3.2 77:01.76 bigcommand
20284 root 25 5 98.7m 932 644 D 2.7 0.0 0:00.96 updatedb

Now let's look at another example."""

        regions = self.detector.detect(text)
        lines = text.split('\n')

        # Should detect the ps output block
        assert len(regions) >= 1
        # Lines 4-6 (0-indexed) contain the code
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 4 in code_lines  # $ ps aux
        assert 5 in code_lines  # 10432 chris...
        assert 6 in code_lines  # 20284 root...

    def test_detects_shell_prompts(self):
        """Lines starting with $ or # should be detected"""
        text = """To install, run:

$ pip install package
$ python setup.py

Then configure."""

        regions = self.detector.detect(text)
        lines = text.split('\n')

        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 2 in code_lines  # $ pip install
        assert 3 in code_lines  # $ python setup.py

    def test_detects_indented_code_blocks(self):
        """Consistently indented blocks should be detected"""
        text = """Here's the code:

    def hello():
        print("world")
        return True

And here's more text."""

        regions = self.detector.detect(text)

        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 2 in code_lines  # def hello():
        assert 3 in code_lines  # print
        assert 4 in code_lines  # return

    def test_ignores_regular_prose(self):
        """Normal paragraphs should not be detected as code"""
        text = """Chapter 1 Introduction

This book teaches Python programming. You will learn
about variables, functions, and classes. Each chapter
builds on the previous one.

Chapter 2 Getting Started

Let's begin with the basics."""

        regions = self.detector.detect(text)

        # Should have no or minimal code regions in prose
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        # Chapter headers and prose should not be in code regions
        assert 0 not in code_lines  # Chapter 1
        assert 2 not in code_lines  # This book teaches
        assert 6 not in code_lines  # Chapter 2

    def test_is_code_line_helper(self):
        """Test individual line detection"""
        assert self.detector.is_code_line("$ pip install foo")
        assert self.detector.is_code_line(">>> print('hello')")
        assert self.detector.is_code_line("    def foo():")
        assert self.detector.is_code_line("10432 chris 20 0 471m")
        assert not self.detector.is_code_line("Chapter 1 Introduction")
        assert not self.detector.is_code_line("This is a normal sentence.")
