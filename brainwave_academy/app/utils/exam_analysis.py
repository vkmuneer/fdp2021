"""Exam result computation: per-student totals/grade/rank and per-subject
stats, shared by the on-screen analysis page, the PDF report card, and the
PDF class analysis report so all three always agree."""
from ..models import ExamMark, grade_for_percentage
from .charts import bar_chart, pie_chart


def compute_exam_results(exam, students):
    """Returns a list of dicts (one per student), ranked best-first by total
    marks. A student is 'Incomplete' until every exam subject has a mark
    recorded for them - incomplete students are excluded from ranking and
    sorted to the end."""
    exam_subjects = exam.exam_subjects
    total_max = sum(es.max_marks for es in exam_subjects)

    results = []
    for student in students:
        marks_by_subject = {
            es.id: ExamMark.query.filter_by(exam_subject_id=es.id, student_id=student.id).first()
            for es in exam_subjects
        }
        entered = [m for m in marks_by_subject.values() if m is not None]
        complete = bool(exam_subjects) and len(entered) == len(exam_subjects)
        total_obtained = sum(m.marks_obtained for m in entered)
        percentage = round(total_obtained / total_max * 100, 1) if total_max else 0
        failed_subjects = [
            marks_by_subject[es.id].exam_subject.subject.name
            for es in exam_subjects
            if marks_by_subject[es.id] and not marks_by_subject[es.id].is_pass
        ]

        if not complete:
            status = "Incomplete"
        elif failed_subjects:
            status = "Fail"
        else:
            status = "Pass"

        results.append(
            {
                "student": student,
                "marks_by_subject": marks_by_subject,
                "total_obtained": total_obtained,
                "total_max": total_max,
                "percentage": percentage,
                "grade": grade_for_percentage(percentage) if complete else "-",
                "failed_subjects": failed_subjects,
                "status": status,
                "complete": complete,
                "rank": None,
            }
        )

    complete_results = sorted(
        [r for r in results if r["complete"]], key=lambda r: r["total_obtained"], reverse=True
    )
    rank, prev_score = 0, None
    for i, r in enumerate(complete_results, start=1):
        if r["total_obtained"] != prev_score:
            rank = i
        r["rank"] = rank
        prev_score = r["total_obtained"]

    results.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 0))
    return results


def subject_analysis(exam, student_ids):
    """Per-subject stats (average %, highest, lowest, pass %) across the
    given student ids."""
    stats = []
    for es in exam.exam_subjects:
        marks = ExamMark.query.filter(
            ExamMark.exam_subject_id == es.id, ExamMark.student_id.in_(student_ids)
        ).all()
        if marks:
            average_pct = round(sum(m.percentage for m in marks) / len(marks), 1)
            highest = max(m.marks_obtained for m in marks)
            lowest = min(m.marks_obtained for m in marks)
            pass_pct = round(sum(1 for m in marks if m.is_pass) / len(marks) * 100, 1)
        else:
            average_pct = highest = lowest = pass_pct = 0

        stats.append(
            {
                "subject": es.subject.name,
                "exam_subject": es,
                "average_pct": average_pct,
                "highest": highest,
                "lowest": lowest,
                "pass_pct": pass_pct,
                "entered_count": len(marks),
            }
        )
    return stats


def build_report_context(exam, students):
    """Full analysis bundle (results, subject stats, pass/fail counts and
    chart images) for the given exam/students - used identically by the
    on-screen report, the PDF analysis report, and both admin/teacher
    blueprints so they can never disagree."""
    results = compute_exam_results(exam, students)
    stats = subject_analysis(exam, [s.id for s in students])
    complete_results = [r for r in results if r["complete"]]
    pass_count = sum(1 for r in complete_results if r["status"] == "Pass")
    fail_count = sum(1 for r in complete_results if r["status"] == "Fail")

    charts = {}
    if stats:
        charts["subject_avg"] = bar_chart(
            [s["subject"] for s in stats], [s["average_pct"] for s in stats], "Average Marks by Subject (%)"
        )
    if complete_results:
        charts["pass_fail"] = pie_chart(["Pass", "Fail"], [pass_count, fail_count], "Pass / Fail")

    return {
        "results": results,
        "stats": stats,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "incomplete_count": len(results) - len(complete_results),
        "charts": charts,
    }
