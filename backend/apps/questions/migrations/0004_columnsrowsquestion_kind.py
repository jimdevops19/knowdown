"""A grid gains a ``kind``: where its accepted answers come from.

Every grid that exists was written with its answers in the resource file, and
``authored`` — the default the column takes — is that. The new value, ``teams``,
is the grid whose answers are looked up in ``apps.questions.rosters`` instead,
so no existing row means anything different after this runs.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('questions', '0003_matrix_cell_answers'),
    ]

    operations = [
        migrations.AddField(
            model_name='columnsrowsquestion',
            name='kind',
            field=models.CharField(choices=[('authored', 'Authored answers'), ('teams', 'NBA teams (answers from the roster artifact)')], default='authored', help_text="Where this grid's accepted answers come from.", max_length=16),
        ),
    ]
