# resources

Put PDFs and other documents for a lesson here (lecture notes, a syllabus, a textbook
chapter, past exams). The contents are gitignored; only this README is tracked.

Then tell the tutor what the document is for, for example:

> Use resources/course-notes.pdf as the primary guide for what I should learn (pages 1-60).

or, for a topic already under way:

> Add resources/lecture-7.pdf as a supplementary source for the OpenMP topic.

The tutor registers the file (`state.py source-add`), has the `document-reader` subagent
read it once and write a page-referenced digest (`source-digest`), sends any statements
that look wrong to the researcher, and adjusts the plan without losing progress. Teaching
then uses the digest; the PDF is reopened only for specific pages. If you replace the
file, `prep-status` notices and the tutor re-digests it.
