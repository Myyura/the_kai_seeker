---
name: admission-analysis
description: Guide for analyzing graduate school admission requirements (募集要項). Activate when users ask about application procedures, eligibility, exam subjects, or deadlines for Japanese graduate schools.
trigger: 募集要項,出願,application,admission,出願資格,試験科目,受験,申请,报名,入試要項
allowed-tools: web_fetch search_schools search_questions
metadata:
  author: the-kai-seeker
  version: "1.0"
  tags: [admission, planning]
---

# 募集要項分析ガイド

When helping users understand admission requirements (募集要項), follow this structure:

## Analysis Framework

1. **Basic Information** (基本情報)
   - Official program name (Japanese and English)
   - Degree type (修士/博士)
   - Application period and exam dates

2. **Eligibility** (出願資格)
   - Required degree/expected graduation
   - Language requirements (TOEFL/TOEIC scores if applicable)
   - Special conditions for international students (外国人特別選考)

3. **Exam Structure** (試験科目)
   - Written exam subjects and weighting
   - Whether subjects are elective or mandatory
   - Oral exam / interview details
   - Portfolio or research plan requirements

4. **Important Dates** (重要日程)
   - Application submission deadline
   - Exam dates (summer/winter sessions if applicable)
   - Results announcement date
   - Enrollment deadline

5. **Materials Required** (提出書類)
   - Transcripts, recommendation letters
   - Research plan (研究計画書) guidelines
   - Certificate of expected graduation

## Important Reminders

- Always check the YEAR of the 募集要項 — requirements change annually
- Distinguish between 一般入試, 外国人特別選考, and 社会人入試
- If fetching from a URL, note that the information may be from a specific year
- Encourage users to verify all dates on the official website
- For schools with multiple exam sessions (夏入試/冬入試), clarify which one
