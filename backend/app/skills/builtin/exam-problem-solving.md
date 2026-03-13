---
name: exam-problem-solving
description: Guide for explaining and solving past exam questions (過去問). Activate when users ask to solve, explain, or analyze specific exam problems from The Kai Project database.
trigger: 解説,解答,解く,solve,explain,解题,讲解,过去问,過去問,answer,solution
allowed-tools: search_questions fetch_question search_schools
metadata:
  author: the-kai-seeker
  version: "1.0"
  tags: [exam, problem-solving]
---

# 過去問 解説ガイド

When helping users with past exam questions, follow this approach:

## Problem-Solving Workflow

1. **Identify the question**: Use search_questions to find the question, then fetch_question to get its full content
2. **Read carefully**: Parse the complete problem statement before attempting a solution
3. **Present the solution** following the structure below

## Solution Structure

### Step 1: Problem Summary (問題の概要)
- Restate the problem in simpler terms
- Identify the topic area (e.g., linear algebra, probability, algorithms)
- Note the difficulty level and key concepts involved

### Step 2: Approach (解法のアプローチ)
- Explain the general strategy before diving into details
- Mention relevant theorems, formulas, or techniques
- If multiple approaches exist, briefly mention alternatives

### Step 3: Detailed Solution (詳細な解答)
- Work through the solution step by step
- Show all intermediate calculations
- Explain the reasoning behind each step, not just the mechanics

### Step 4: Key Takeaways (ポイント)
- Summarize the core concept being tested
- Highlight common pitfalls or mistakes
- Suggest related topics to study

## Principles

- **Guide, don't just give answers**: Help users understand *why*, not just *what*
- **Verify the solution**: If the Kai Project already has a solution, compare your approach
- **Adapt to the user's level**: If they're struggling with basics, explain prerequisites first
- **Use the user's language**: Match Chinese/Japanese/English based on the conversation
- **LaTeX formatting**: Use proper LaTeX for mathematical expressions
