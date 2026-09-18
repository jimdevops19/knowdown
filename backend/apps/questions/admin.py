"""The admin exists to *proofread* what the loader wrote.

Questions are authored in YAML and loaded by ``manage.py sync_questions``, so
nothing here is the way a question comes into being. What it is for: opening a
category after a load and reading the questions back the way a player will see
them — which is the only reliable way to catch a wrong answer marked correct.

Editing here is allowed and is deliberately temporary: the next sync overwrites
any field the resource file owns. The comment is the warning; a read-only admin
would remove the one thing it is good for, which is flipping ``is_active`` off
on a question found to be wrong at 9pm.
"""

from __future__ import annotations

from django.contrib import admin

from .models import (
    ColumnsRowsQuestion,
    FreeTextAnswer,
    FreeTextQuestion,
    GradualHint,
    GradualHintsField,
    GradualHintsFieldAnswer,
    GradualHintsQuestion,
    ImageAnswerOption,
    MatrixCell,
    MatrixCellAnswer,
    MatrixColumn,
    MatrixRow,
    MultipleAnswerOption,
    MultipleAnswerQuestion,
    NameAsManyQuestion,
    OrderingOption,
    OrderingQuestion,
    SingleAnswerImageQuestion,
    SingleAnswerOption,
    SingleAnswerQuestion,
    TrueFalseQuestion,
)


class _QuestionAdmin(admin.ModelAdmin):
    """What every question changelist shows, whatever its answer shape.

    ``description`` is the searchable field, not the slug: someone reporting a
    bad question quotes the question, not the key it was authored under.
    """

    list_display = ("slug", "category", "level", "is_active", "updated_at")
    list_filter = ("category", "level", "is_active")
    search_fields = ("slug", "description")
    readonly_fields = ("created_at", "updated_at")


class _OptionInline(admin.TabularInline):
    extra = 0


class SingleAnswerOptionInline(_OptionInline):
    model = SingleAnswerOption


class ImageAnswerOptionInline(_OptionInline):
    model = ImageAnswerOption


class MultipleAnswerOptionInline(_OptionInline):
    model = MultipleAnswerOption


class FreeTextAnswerInline(_OptionInline):
    model = FreeTextAnswer


class OrderingOptionInline(_OptionInline):
    model = OrderingOption


class MatrixRowInline(_OptionInline):
    model = MatrixRow


class MatrixColumnInline(_OptionInline):
    model = MatrixColumn


class MatrixCellInline(_OptionInline):
    model = MatrixCell
    # The grid is read row by row, and a cell is meaningless without both
    # headings — so both are shown, and neither is a free-text field.
    autocomplete_fields = ()
    show_change_link = True  # where its answers are edited, see MatrixCellAdmin


class MatrixCellAnswerInline(_OptionInline):
    model = MatrixCellAnswer


class GradualHintInline(_OptionInline):
    model = GradualHint


class GradualHintsFieldInline(_OptionInline):
    model = GradualHintsField
    show_change_link = True  # where its accepted answers are, see the admin below


class GradualHintsFieldAnswerInline(_OptionInline):
    model = GradualHintsFieldAnswer


@admin.register(SingleAnswerQuestion)
class SingleAnswerQuestionAdmin(_QuestionAdmin):
    inlines = [SingleAnswerOptionInline]


@admin.register(SingleAnswerImageQuestion)
class SingleAnswerImageQuestionAdmin(_QuestionAdmin):
    inlines = [ImageAnswerOptionInline]


@admin.register(MultipleAnswerQuestion)
class MultipleAnswerQuestionAdmin(_QuestionAdmin):
    inlines = [MultipleAnswerOptionInline]


@admin.register(TrueFalseQuestion)
class TrueFalseQuestionAdmin(_QuestionAdmin):
    list_display = (*_QuestionAdmin.list_display, "answer")


@admin.register(FreeTextQuestion)
class FreeTextQuestionAdmin(_QuestionAdmin):
    inlines = [FreeTextAnswerInline]


@admin.register(OrderingQuestion)
class OrderingQuestionAdmin(_QuestionAdmin):
    inlines = [OrderingOptionInline]


@admin.register(NameAsManyQuestion)
class NameAsManyQuestionAdmin(_QuestionAdmin):
    """The one question type with nothing to proofread underneath it.

    There are no inlines because there are no child rows: who qualifies is a
    line through a column of a baked CSV (``apps.questions.career_stats``), not
    a table of answers somebody wrote. So what the changelist shows *is* the
    question — the stat, which way the comparison runs, where the line sits and
    what a full answer costs — and reading a question back here means reading
    those four and asking whether they say what the description says.
    """

    list_display = (
        *_QuestionAdmin.list_display,
        "stat",
        "comparison",
        "threshold",
        "target_score",
    )
    list_filter = (*_QuestionAdmin.list_filter, "dataset", "stat", "comparison")


@admin.register(MatrixCell)
class MatrixCellAdmin(admin.ModelAdmin):
    """Where a cell's accepted answers are graded.

    A cell has its own page rather than being edited entirely inside the
    question, because its answers are its *grand*children and Django has no
    nested inline: the question lists the intersections, and each one links here
    for the several names that fill it and how obscure each of them is.
    """

    list_display = ("question", "row", "column", "answer_count")
    list_filter = ("question__category",)
    search_fields = ("question__slug", "row__title", "column__title")
    inlines = [MatrixCellAnswerInline]

    @admin.display(description="answers")
    def answer_count(self, cell: MatrixCell) -> int:
        return cell.answers.count()


@admin.register(ColumnsRowsQuestion)
class ColumnsRowsQuestionAdmin(_QuestionAdmin):
    """A grid, and where its answers come from.

    ``kind`` is on the list display because it is the difference between a cell
    with no answers being an authoring mistake and it being the normal state of
    a ``teams`` grid, whose answer key is ``apps.questions.rosters`` rather than
    anything editable here.
    """

    list_display = (*_QuestionAdmin.list_display, "kind", "row_count", "column_count")
    list_filter = (*_QuestionAdmin.list_filter, "kind")
    inlines = [MatrixRowInline, MatrixColumnInline, MatrixCellInline]


@admin.register(GradualHintsField)
class GradualHintsFieldAdmin(admin.ModelAdmin):
    """Where one box's accepted spellings are proofread.

    A page of its own for the reason ``MatrixCellAdmin`` has one: the answers
    are the question's *grand*children and Django has no nested inline, so the
    question lists the boxes and each one links here for the spellings that
    fill it. This is the page to open when a player says a right answer was
    marked wrong.
    """

    list_display = ("question", "order", "label", "kind", "answer_count")
    list_filter = ("kind", "question__category")
    search_fields = ("question__slug", "label")
    inlines = [GradualHintsFieldAnswerInline]

    @admin.display(description="accepted answers")
    def answer_count(self, field: GradualHintsField) -> int:
        return field.accepted_answers.count()


@admin.register(GradualHintsQuestion)
class GradualHintsQuestionAdmin(_QuestionAdmin):
    """The clues, in reveal order, and the boxes they lead to.

    ``hint_interval_seconds`` is on the list display because it is the one
    number here that changes how the question *plays* rather than what it says:
    the same five clues at three seconds and at fifteen are two different
    questions, and the second may not fit its clock at all (the loader refuses
    that — ``schemas.GradualHintsSpec``).
    """

    list_display = (*_QuestionAdmin.list_display, "hint_interval_seconds")
    inlines = [GradualHintInline, GradualHintsFieldInline]
