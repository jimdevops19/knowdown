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
    ImageAnswerOption,
    MatrixCell,
    MatrixColumn,
    MatrixRow,
    MultipleAnswerOption,
    MultipleAnswerQuestion,
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


@admin.register(ColumnsRowsQuestion)
class ColumnsRowsQuestionAdmin(_QuestionAdmin):
    list_display = (*_QuestionAdmin.list_display, "row_count", "column_count")
    inlines = [MatrixRowInline, MatrixColumnInline, MatrixCellInline]
