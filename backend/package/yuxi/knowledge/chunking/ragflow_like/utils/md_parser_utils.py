from __future__ import annotations

import re
from typing import List, Callable, Any
from .semantic_utils import semantic_chunking_with_auto_clusters

def infer_heading_level(title: str) -> int:
    """
    根据标题文本推断其层级级别（1-6级）。
    """
    m = re.match(r'^\s*(\d+(?:\.\d+)*)[.)、]?\s*', title)
    if m:
        return max(1, min(len(m.group(1).split('.')), 6))
    m_zh = re.match(r'^\s*[一二三四五六七八九十百千]+[、.]\s*', title)
    if m_zh:
        return 1
    return 1

def get_title_path(stack: List[str]) -> str:
    """
    根据标题栈生成标题路径，用"|"分隔。
    """
    return '|'.join([t for t in stack if t])

def extract_table_block(tokens: List[Any], i: int, original_lines: List[str]) -> tuple[int, str]:
    """
    从token流和原始文本中提取完整的表格块。
    """
    token = tokens[i]
    table_start = token.map[0] if token.map else 0
    j = i + 1
    while j < len(tokens) and tokens[j].type != 'table_close':
        j += 1
    if j < len(tokens):
        end_token = tokens[j]
        if end_token.map and end_token.map[1] is not None:
            table_end = end_token.map[1]
        else:
            table_end = None
            for k in range(j + 1, len(tokens)):
                if tokens[k].map and tokens[k].map[0] is not None:
                    table_end = tokens[k].map[0]
                    break
            if table_end is None:
                table_end = table_start + 1
                for line_idx in range(table_start, len(original_lines)):
                    line = original_lines[line_idx].strip()
                    if not line or not (line.startswith('|') or '|' in line):
                        table_end = line_idx
                        break
    else:
        table_end = table_start + 1
        for line_idx in range(table_start, len(original_lines)):
            line = original_lines[line_idx].strip()
            if not line or not (line.startswith('|') or '|' in line):
                table_end = line_idx
                break
    return j, '\n'.join(original_lines[table_start:table_end])

def split_text_by_length_and_newline(
    text: str, 
    max_length: int,
    embed_fn: Callable[[List[str]], Any],
    token_count_fn: Callable[[str], int]
) -> List[str]:
    """
    层次化文本切分策略。
    """
    chunks = []
    
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        paragraph_token_count = token_count_fn(paragraph)

        if paragraph_token_count <= max_length:
            chunks.append(paragraph)
            continue
        
        lines = paragraph.split('\n')
        current_chunk_lines = []
        current_chunk_tokens = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_token_count = token_count_fn(line)
            added_tokens = line_token_count + (1 if current_chunk_lines else 0)
            
            if line_token_count > max_length:
                if current_chunk_lines:
                    chunks.append('\n'.join(current_chunk_lines))
                    current_chunk_lines = []
                    current_chunk_tokens = 0
                
                sub_chunks = semantic_chunking_with_auto_clusters(
                    line, 
                    embed_fn=embed_fn, 
                    token_count_fn=token_count_fn, 
                    max_chunk_size=max_length
                )
                chunks.extend(sub_chunks)
            
            elif current_chunk_tokens + added_tokens > max_length:
                chunks.append('\n'.join(current_chunk_lines))
                current_chunk_lines = [line]
                current_chunk_tokens = line_token_count
            
            else:
                current_chunk_lines.append(line)
                current_chunk_tokens += added_tokens
        
        if current_chunk_lines:
            chunks.append('\n'.join(current_chunk_lines))
    
    return chunks
