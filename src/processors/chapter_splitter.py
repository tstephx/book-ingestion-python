"""Chapter splitting logic with improved detection"""

import re

class ChapterSplitter:
    def __init__(self, config):
        self.config = config.chapter_detection
        self.patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.config['patterns']]

    def split(self, text, book_id):
        """Split text into chapters"""
        # Try TOC-based detection first (most reliable for Packt-style books)
        toc_matches = self._detect_from_toc(text)
        if len(toc_matches) >= 5:
            # Sort by line index
            toc_matches.sort(key=lambda x: x['index'])
            return self._build_chapters_from_matches(text, book_id, toc_matches)

        # Fall back to pattern-based detection
        lines = text.split('\n')
        matches = []

        # Find chapter markers
        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip very short lines (likely not chapter headers)
            if len(line_stripped) < 3:
                continue

            # Skip lines that are too long (likely not chapter headers)
            if len(line_stripped) > 100:
                continue

            for pattern in self.patterns:
                if pattern.match(line_stripped):
                    # Additional validation to avoid false positives
                    if not self._is_likely_chapter_header(line_stripped, lines, i):
                        continue

                    # Clean up the title
                    title = line_stripped
                    # Remove excessive whitespace
                    title = re.sub(r'\s+', ' ', title).strip()

                    matches.append({
                        'index': i,
                        'title': title
                    })
                    break

        # If very few chapters found, try more lenient matching
        if len(matches) < 3:
            return self._lenient_split(text, book_id, matches)
        
        # Extract chapters based on markers
        chapters = []
        for idx, match in enumerate(matches):
            start = match['index'] + 1
            end = matches[idx + 1]['index'] if idx + 1 < len(matches) else len(lines)
            
            content = '\n'.join(lines[start:end]).strip()
            word_count = len(content.split())
            
            # Skip very short chapters (unless it's the only one)
            if word_count < self.config['min_words_per_chapter'] and len(matches) > 1:
                continue
            
            # Skip very long chapters (might be bad detection)
            if word_count > self.config['max_words_per_chapter']:
                continue
            
            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': match['title'],
                'content': content,
                'word_count': word_count,
                'file_path': ''
            })
        
        # If still no valid chapters, use fixed-size splitting
        if len(chapters) == 0:
            return self._fixed_size_split(text, book_id)
        
        return chapters
    
    def _lenient_split(self, text, book_id, existing_matches):
        """
        Try more lenient chapter detection when few chapters found
        """
        lines = text.split('\n')
        matches = list(existing_matches)  # Copy existing matches

        # Additional lenient patterns
        lenient_patterns = [
            r'^\d+\s*$',  # Just a number on its own line
            r'^[A-Z][A-Z\s]{10,}$',  # ALL CAPS HEADINGS
            r'^\*\*\s*Chapter',  # Markdown-style chapters
        ]

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            if len(line_stripped) < 2 or len(line_stripped) > 80:
                continue

            # Check if already matched
            if any(m['index'] == i for m in matches):
                continue

            for pattern in lenient_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    matches.append({
                        'index': i,
                        'title': line_stripped
                    })
                    break

        # If still too few, try title-based detection
        if len(matches) < 3:
            title_matches = self._detect_title_chapters(text, book_id)
            if len(title_matches) >= 3:
                matches = title_matches

        # If still too few, use fixed-size
        if len(matches) < 3:
            return self._fixed_size_split(text, book_id)

        # Sort matches by index to ensure correct order
        matches.sort(key=lambda x: x['index'])

        # Process matches (same as above)
        chapters = []
        for idx, match in enumerate(matches):
            start = match['index'] + 1
            end = matches[idx + 1]['index'] if idx + 1 < len(matches) else len(lines)
            
            content = '\n'.join(lines[start:end]).strip()
            word_count = len(content.split())
            
            if word_count < self.config['min_words_per_chapter']:
                continue
            
            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': match['title'],
                'content': content,
                'word_count': word_count,
                'file_path': ''
            })
        
        return chapters if len(chapters) > 0 else self._fixed_size_split(text, book_id)
    
    def _build_chapters_from_matches(self, text, book_id, matches):
        """Build chapter objects from a list of matches"""
        lines = text.split('\n')
        chapters = []

        for idx, match in enumerate(matches):
            start = match['index'] + 1
            end = matches[idx + 1]['index'] if idx + 1 < len(matches) else len(lines)

            content = '\n'.join(lines[start:end]).strip()
            word_count = len(content.split())

            # Skip chapters that are too short or too long
            if word_count < self.config['min_words_per_chapter'] and len(matches) > 1:
                continue
            if word_count > self.config['max_words_per_chapter']:
                continue

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': match['title'],
                'content': content,
                'word_count': word_count,
                'file_path': ''
            })

        return chapters if chapters else self._fixed_size_split(text, book_id)

    def _fixed_size_split(self, text, book_id):
        """Split into fixed-size chunks when no chapters detected"""
        words = text.split()
        chunk_size = 2500
        chapters = []

        for i in range(0, len(words), chunk_size):
            content = ' '.join(words[i:i + chunk_size])

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': f"Section {len(chapters) + 1}",
                'content': content,
                'word_count': len(content.split()),
                'file_path': ''
            })

        return chapters

    def _is_likely_chapter_header(self, line, lines, index):
        """
        Validate if a line is likely a real chapter header vs a numbered list item.
        Returns True if it looks like a chapter header, False otherwise.
        """
        # Filter out code file paths like "Chapter 2/solution.py" or "Chapter 3/test.js"
        if re.match(r'^Chapter\s+\d+/[\w\-\.]+\.\w+$', line, re.IGNORECASE):
            return False

        # Filter out any line containing a file path pattern (forward slash followed by filename)
        if re.search(r'/[\w\-\.]+\.\w{1,4}$', line):
            return False

        # Check for numbered patterns - these need strict validation
        is_numbered = re.match(r'^(\d+)[\.\s]+[A-Z]', line)

        if is_numbered:
            # Chapter headers are usually < 60 chars (short titles)
            if len(line) > 60:
                return False

            # Must be preceded by blank line
            if index > 0 and lines[index - 1].strip() != '':
                return False

            # If it's a list item (nearby lines are also numbered), skip it
            if index > 0:
                prev_line = lines[index - 1].strip()
                if re.match(r'^(\d+)[\.\s]+', prev_line):
                    return False

            if index < len(lines) - 1:
                next_line = lines[index + 1].strip()
                if re.match(r'^(\d+)[\.\s]+', next_line):
                    return False

            # Check lines within a small window for numbered patterns (list detection)
            nearby_numbered = 0
            for j in range(max(0, index - 3), min(len(lines), index + 4)):
                if j != index and re.match(r'^(\d+)[\.\s]+', lines[j].strip()):
                    nearby_numbered += 1
            if nearby_numbered >= 2:
                return False

        return True

    def _detect_title_chapters(self, text, book_id):
        """
        Detect chapters by looking for title-style headers.
        First tries TOC-based detection, then falls back to heuristics.
        """
        # Try TOC-based detection first
        toc_matches = self._detect_from_toc(text)
        if len(toc_matches) >= 3:
            return toc_matches

        # Fallback to heuristic title detection
        return self._detect_title_heuristic(text)

    def _detect_from_toc(self, text):
        """
        Extract chapter titles from Table of Contents and find them in body.
        Supports multiple TOC formats.
        """
        lines = text.split('\n')

        # Patterns for different TOC formats
        toc_patterns = [
            # Packt style: "Chapter X, Title, description..."
            (re.compile(r'^Chapter\s+(\d+),\s+([^,]+)', re.IGNORECASE), 2),
            # Apress style: "Chapter X: Title...page" or "Chapter X: Title"
            (re.compile(r'^Chapter\s+(\d+):\s+([^\.]+?)(?:\.{2,}|\s*$)', re.IGNORECASE), 2),
            # Project style: "Project XA: Title"
            (re.compile(r'^Project\s+(\d+[A-Z]):\s+(.+)', re.IGNORECASE), 2),
        ]

        # Try each pattern to find chapter titles in TOC
        chapter_titles = []
        for toc_pattern, title_group in toc_patterns:
            chapter_titles = []
            for line in lines[:400]:  # Extended for longer TOCs
                match = toc_pattern.match(line.strip())
                if match:
                    # Strip whitespace from title
                    title = match.group(title_group).strip()
                    # Remove any trailing punctuation or whitespace
                    title = title.rstrip(' \t\n\r')
                    chapter_titles.append(title)

            # If we found enough chapters with this pattern, use it
            if len(chapter_titles) >= 3:
                break

        if len(chapter_titles) < 3:
            return []

        matches = []
        # Track used line indices to avoid duplicates
        used_indices = set()
        # Track the last found chapter position to search sequentially
        last_found_index = 300

        # Find each title in the body
        for title in chapter_titles:
            # Extract key words from title (3+ chars, not common words)
            stop_words = {'the', 'and', 'with', 'for', 'from', 'into', 'that'}
            key_words = [w.lower() for w in re.findall(r'\b\w{3,}\b', title)
                        if w.lower() not in stop_words]

            # Keep searching until we find a valid match or exhaust options
            found_valid = False
            max_attempts = 5  # Prevent infinite loops

            for attempt in range(max_attempts):
                if found_valid:
                    break

                best_match = None
                best_score = 0

                # Search for lines containing most key words (start after last found)
                for i, line in enumerate(lines[last_found_index:], start=last_found_index):
                    # Skip already used indices
                    if i in used_indices:
                        continue

                    line_stripped = line.strip()
                    line_lower = line_stripped.lower()

                    # Skip long lines (not headers) or very short lines
                    if len(line_stripped) > 80 or len(line_stripped) < 15:
                        continue

                    # Check exact match first (highest priority)
                    if title in line_stripped:
                        best_match = {'index': i, 'title': line_stripped}
                        best_score = 1.0
                        break

                    # Check if titles share the same prefix (first 2-3 significant words)
                    title_prefix = ' '.join(title.split()[:3]).lower()
                    line_prefix = ' '.join(line_stripped.split()[:3]).lower()
                    if title_prefix == line_prefix and len(title_prefix) > 10:
                        best_match = {'index': i, 'title': line_stripped}
                        best_score = 0.9
                        break

                    # Check fuzzy match
                    if key_words and len(key_words) >= 2:
                        matches_found = sum(1 for kw in key_words if kw in line_lower)
                        match_ratio = matches_found / len(key_words)

                        # Need at least 60% of key words AND at least 2 matches
                        if match_ratio >= 0.6 and matches_found >= 2:
                            # Additional check: line should look like a title (title case)
                            words = line_stripped.split()
                            if len(words) >= 3:
                                title_words = [w for w in words if len(w) > 2]
                                if title_words:
                                    upper_count = sum(1 for w in title_words if w[0].isupper())
                                    if upper_count / len(title_words) >= 0.7:
                                        if match_ratio > best_score:
                                            best_match = {'index': i, 'title': line_stripped}
                                            best_score = match_ratio

                if best_match:
                    # Verify this match has substantial content (not a TOC entry)
                    check_start = best_match['index'] + 1
                    check_end = min(check_start + 50, len(lines))
                    content_sample = ' '.join(lines[check_start:check_end])
                    word_count = len(content_sample.split())

                    if word_count >= 150:
                        matches.append(best_match)
                        used_indices.add(best_match['index'])
                        last_found_index = best_match['index'] + 1
                        found_valid = True
                    else:
                        # Reject this TOC entry and try again
                        used_indices.add(best_match['index'])
                else:
                    # No more matches found for this title
                    break

        return matches

    def _detect_title_heuristic(self, text):
        """
        Fallback heuristic detection for title-style chapter headers.
        """
        lines = text.split('\n')
        matches = []

        skip_patterns = [
            r'^(Figure|Table|Example|Note|Warning|Tip|Important|Summary|Conclusion)\s',
            r'^(Copyright|License|ISBN|Published|Printed)',
            r'^\d+\.\d+',  # Version numbers
            r'^https?://',  # URLs
        ]

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            if len(line_stripped) < 15 or len(line_stripped) > 70:
                continue

            if i > 2 and lines[i - 1].strip() != '':
                continue

            if any(re.match(p, line_stripped, re.IGNORECASE) for p in skip_patterns):
                continue

            words = line_stripped.split()
            if len(words) < 3:
                continue

            # Title case check
            title_words = [w for w in words if len(w) > 3]
            if title_words:
                upper_ratio = sum(1 for w in title_words if w[0].isupper()) / len(title_words)
                if upper_ratio >= 0.8 and ':' in line_stripped:
                    matches.append({
                        'index': i,
                        'title': line_stripped
                    })

        return matches
