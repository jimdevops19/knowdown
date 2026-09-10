"""A matrix cell stops holding one answer and starts holding several.

Ordered so no answer is lost: the new table is created, every existing cell's
single answer is copied onto a row of it, and only then is the old column
dropped.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

#: ``models.DEFAULT_PROBABILITY_SCORE`` as it stood when this migration was
#: written. Copied rather than imported: a migration has to keep running after
#: the constant it was written against moves or changes value.
DEFAULT_PROBABILITY_SCORE = 5


def _move_answers_onto_their_own_rows(apps, schema_editor):
    """One answer per cell becomes one ``MatrixCellAnswer`` row.

    Every cell that already exists was authored under the old one-answer rule,
    so each becomes a single accepted answer graded
    ``DEFAULT_PROBABILITY_SCORE`` — ungraded, which is what the middle of the
    scale means. Re-running ``sync_questions`` is what replaces these with the
    answers and grades the resource files now carry.
    """
    MatrixCell = apps.get_model("questions", "MatrixCell")
    MatrixCellAnswer = apps.get_model("questions", "MatrixCellAnswer")
    MatrixCellAnswer.objects.bulk_create(
        MatrixCellAnswer(
            cell_id=cell_id,
            value=answer,
            probability_score=DEFAULT_PROBABILITY_SCORE,
        )
        for cell_id, answer in MatrixCell.objects.values_list("id", "answer")
        if answer
    )


def _move_answers_back(apps, schema_editor):
    """The reverse: each cell keeps whichever of its answers is most obvious.

    Lossy by nature — the old column holds one answer where the new table holds
    several — so the one kept is the lowest ``probability_score``, the same pick
    a bot makes.
    """
    MatrixCell = apps.get_model("questions", "MatrixCell")
    for cell in MatrixCell.objects.all():
        answer = cell.answers.order_by("probability_score", "value").first()
        if answer is not None:
            cell.answer = answer.value
            cell.save(update_fields=["answer"])


class Migration(migrations.Migration):
    dependencies = [
        ("questions", "0002_columnsrowsquestion_time_limit_seconds_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MatrixCellAnswer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", models.CharField(max_length=255)),
                (
                    "probability_score",
                    models.PositiveSmallIntegerField(
                        default=5,
                        help_text=(
                            "How obscure this pick is: 2 (everybody says it) to "
                            "10 (deep cut)."
                        ),
                        validators=[
                            django.core.validators.MinValueValidator(2),
                            django.core.validators.MaxValueValidator(10),
                        ],
                    ),
                ),
                (
                    "cell",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="questions.matrixcell",
                    ),
                ),
            ],
            options={
                "ordering": ("probability_score", "value"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("cell", "value"), name="uniq_matrix_cell_answer_value"
                    )
                ],
            },
        ),
        migrations.RunPython(
            _move_answers_onto_their_own_rows,
            _move_answers_back,
        ),
        migrations.RemoveField(
            model_name="matrixcell",
            name="answer",
        ),
    ]
