# Knowdown — Django Project Structure

## Product Goal

Knowdown is a real-time 1v1 trivia game where all online players enter **one global matchmaking pool**.

The core loop:

```text
Player opens app
      ↓
Global matchmaking pool
      ↓
Player A ↔ Player B
      ↓
Random 3 / 5 / 7 questions
      ↓
Same question shown to both
      ↓
Fastest correct answer
      ↓
Winner / Loser
      ↓
Ranking + Achievements
      ↓
Both return to global pool
```

The initial category is **NBA**, but categories must remain independent from the question types so the system can later support Premier League, F1, UFC, etc.

---

# Project Structure

```text
rival/
├── manage.py
├── pyproject.toml
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── account/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   │
│   ├── player/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── selectors.py
│   │   └── services.py
│   │
│   ├── category/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── selectors.py
│   │
│   ├── questions/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── multiple_choice.py
│   │   │   ├── free_text.py
│   │   │   ├── ordering.py
│   │   │   └── matrix.py
│   │   ├── selectors.py
│   │   ├── services.py
│   │   └── validators.py
│   │
│   ├── match/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── constants.py
│   │   ├── models.py
│   │   ├── consumers.py
│   │   ├── routing.py
│   │   ├── selectors.py
│   │   └── services.py
│   │
│   ├── rankings/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── selectors.py
│   │   └── services.py
│   │
│   └── achievements/
│       ├── migrations/
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── selectors.py
│       └── services.py
│
├── tests/
│   ├── account/
│   ├── player/
│   ├── category/
│   ├── questions/
│   ├── match/
│   ├── rankings/
│   └── achievements/
│
└── media/
    ├── questions/
    ├── questions/answers/
    ├── players/avatars/
    └── achievements/
```

---

# 1. Account

Owns authentication.

```text
Authentication
OAuth
Email
Account status
Login / logout
Account deletion
```

Keep authentication separate from the game profile.

---

# 2. Player

Represents a person playing Rival.

```python
class Player(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="player",
    )

    display_name = models.CharField(max_length=30)

    avatar = models.ImageField(
        upload_to="players/avatars/",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Keep game-specific statistics out of `Player` unless there is a real reason to denormalize them.

---

# 3. Category

Categories describe the subject of questions.

Initially:

```text
NBA
```

Later:

```text
NBA
Premier League
F1
UFC
NFL
```

```python
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    slug = models.SlugField(unique=True)

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
```

A question belongs to a category.

---

# 4. Questions

The question system describes **how a player answers**, while the category describes **what the question is about**.

```text
BaseQuestion
│
├── MultipleChoiceQuestion
│   ├── SingleAnswerQuestion
│   ├── SingleAnswerImageQuestion
│   └── MultipleAnswerQuestion
│
├── TrueFalseQuestion
├── FreeTextQuestion
├── OrderingQuestion
└── ColumnsRowsQuestion
```

---

## BaseQuestion

```python
class BaseQuestion(models.Model):
    description = models.TextField()

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.PROTECT,
        related_name="questions",
    )

    tags = models.JSONField(
        default=dict,
        blank=True,
    )

    level = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10),
        ],
    )

    image = models.ImageField(
        upload_to="questions/",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

Example tags:

```json
{
  "subcategory": "nba-history",
  "topic": "players",
  "era": "2000s"
}
```

---

## SingleAnswerQuestion

```python
class MultipleChoiceQuestion(BaseQuestion):
    class Meta:
        abstract = True


class SingleAnswerQuestion(MultipleChoiceQuestion):
    pass
```

```python
class SingleAnswerOption(models.Model):
    question = models.ForeignKey(
        SingleAnswerQuestion,
        on_delete=models.CASCADE,
        related_name="options",
    )

    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField()
```

Exactly one option should be correct.

---

## SingleAnswerImageQuestion

```python
class SingleAnswerImageQuestion(MultipleChoiceQuestion):
    pass
```

```python
class ImageAnswerOption(models.Model):
    question = models.ForeignKey(
        SingleAnswerImageQuestion,
        on_delete=models.CASCADE,
        related_name="options",
    )

    image = models.ImageField(
        upload_to="questions/answers/",
    )

    label = models.CharField(
        max_length=255,
        blank=True,
    )

    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField()
```

Useful for questions such as:

> Which NBA player is shown?

---

## MultipleAnswerQuestion

```python
class MultipleAnswerQuestion(MultipleChoiceQuestion):
    pass
```

Multiple options can be correct.

Submitted answer can contain multiple option IDs:

```json
{
  "option_ids": [2, 5, 9]
}
```

---

## TrueFalseQuestion

```python
class TrueFalseQuestion(BaseQuestion):
    answer = models.BooleanField()
```

---

## FreeTextQuestion

```python
class FreeTextQuestion(BaseQuestion):
    pass
```

Accepted answers:

```python
class FreeTextAnswer(models.Model):
    question = models.ForeignKey(
        FreeTextQuestion,
        on_delete=models.CASCADE,
        related_name="accepted_answers",
    )

    value = models.CharField(max_length=255)
```

This allows:

```text
Kobe Bryant
Kobe
```

to both be accepted.

---

## OrderingQuestion

Example:

> Order these players from highest to lowest single-game scoring performance.

```python
class OrderingQuestion(BaseQuestion):
    instruction = models.TextField()
```

```python
class OrderingOption(models.Model):
    question = models.ForeignKey(
        OrderingQuestion,
        on_delete=models.CASCADE,
        related_name="options",
    )

    text = models.CharField(max_length=255)

    correct_position = models.PositiveSmallIntegerField()
```

The frontend can randomize the displayed order.

The backend stores the correct order.

---

## ColumnsRowsQuestion

Matrix-style questions.

Example:

```text
                 Miami Heat   Phoenix Suns   Lakers
Miami Heat            -             ?             ?
Phoenix Suns          ?             -             ?
Lakers                ?             ?             -
```

A cell may have:

```text
Miami Heat × Phoenix Suns
→ LeBron James
```

Model:

```python
class ColumnsRowsQuestion(BaseQuestion):
    row_count = models.PositiveSmallIntegerField()
    column_count = models.PositiveSmallIntegerField()
```

Rows:

```python
class MatrixRow(models.Model):
    question = models.ForeignKey(
        ColumnsRowsQuestion,
        on_delete=models.CASCADE,
        related_name="rows",
    )

    title = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField()
```

Columns:

```python
class MatrixColumn(models.Model):
    question = models.ForeignKey(
        ColumnsRowsQuestion,
        on_delete=models.CASCADE,
        related_name="columns",
    )

    title = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField()
```

Cells:

```python
class MatrixCell(models.Model):
    question = models.ForeignKey(
        ColumnsRowsQuestion,
        on_delete=models.CASCADE,
        related_name="cells",
    )

    row = models.ForeignKey(
        MatrixRow,
        on_delete=models.CASCADE,
        related_name="cells",
    )

    column = models.ForeignKey(
        MatrixColumn,
        on_delete=models.CASCADE,
        related_name="cells",
    )

    answer = models.CharField(max_length=255)
```

Do **not** create separate models for 2×2, 2×3 and 3×3.

Use:

```text
row_count = 2
column_count = 2
```

or:

```text
row_count = 3
column_count = 3
```

---

# 5. Match

The `match` app owns the competitive game.

```text
Global Matchmaking Pool
        ↓
Player A + Player B
        ↓
Matchup
        ↓
Matchup Questions
        ↓
Player Answers
        ↓
Result
```

---

## Match constants

```python
MATCH_QUESTION_COUNTS = (3, 5, 7)

MAX_PLAYERS_PER_MATCHUP = 2

DEFAULT_PLAYER_RATING = 1000

QUESTION_TIME_LIMIT_SECONDS = 10
```

For each new matchup:

```python
question_count = random.choice(
    MATCH_QUESTION_COUNTS,
)
```

Therefore:

```text
Match A → 3 questions
Match B → 7 questions
Match C → 5 questions
```

The server chooses this value.

---

## Matchup

```python
class Matchup(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting"
        ACTIVE = "active"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.PROTECT,
        related_name="matchups",
    )

    question_count = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.WAITING,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
```

---

## MatchupPlayer

```python
class MatchupPlayer(models.Model):
    matchup = models.ForeignKey(
        Matchup,
        on_delete=models.CASCADE,
        related_name="players",
    )

    player = models.ForeignKey(
        "player.Player",
        on_delete=models.PROTECT,
        related_name="matchups",
    )

    score = models.PositiveIntegerField(default=0)

    correct_answers = models.PositiveIntegerField(default=0)

    total_answer_time_ms = models.PositiveBigIntegerField(default=0)

    is_winner = models.BooleanField(default=False)

    joined_at = models.DateTimeField(auto_now_add=True)
```

A matchup must contain exactly two players.

---

## MatchupQuestion

A matchup should preserve the exact questions played in that game.

```python
class MatchupQuestion(models.Model):
    matchup = models.ForeignKey(
        Matchup,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    question_id = models.PositiveBigIntegerField()

    question_type = models.CharField(max_length=50)

    order = models.PositiveSmallIntegerField()

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
```

The pair:

```text
question_type
question_id
```

identifies the concrete question.

---

## PlayerAnswer

```python
class PlayerAnswer(models.Model):
    matchup_question = models.ForeignKey(
        MatchupQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    player = models.ForeignKey(
        "player.Player",
        on_delete=models.PROTECT,
        related_name="answers",
    )

    answer = models.JSONField()

    is_correct = models.BooleanField()

    response_time_ms = models.PositiveBigIntegerField()

    answered_at = models.DateTimeField(
        auto_now_add=True,
    )
```

Example payloads:

```json
{"option_id": 12}
```

```json
{"option_ids": [12, 15]}
```

```json
{"value": "Kobe Bryant"}
```

```json
{"option_ids": [12, 4, 9]}
```

```json
{
  "row_id": 2,
  "column_id": 5,
  "value": "LeBron James"
}
```

---

# Global Matchmaking

There should be **one logical global pool**.

Do not create a database room for every player.

Conceptually:

```text
ONLINE PLAYERS

[A] [B] [C] [D] [E] [F] [G]
             ↓
       Matchmaking
             ↓
         [C] vs [F]
```

After the matchup:

```text
[C] ──┐
      ├── Match complete
[F] ──┘
      ↓
Both return to the global pool
```

---

# Realtime State

Use Redis + Django Channels for transient state.

Examples:

```text
ONLINE
SEARCHING
MATCHED
PLAYING
OFFLINE
```

Redis handles:

```text
Global matchmaking queue
Online players
WebSocket connections
Active matchup state
Current question
Timers
```

PostgreSQL handles the permanent history.

---

# WebSocket Flow

## Enter matchmaking

```text
CONNECT
   ↓
Authenticate
   ↓
Mark ONLINE
   ↓
Enter global matchmaking queue
```

## Match found

```text
Player A searching
Player B searching
        ↓
Matchmaker pairs them
        ↓
Create Matchup
        ↓
Choose 3 / 5 / 7
        ↓
Select questions
        ↓
Create WebSocket group
        ↓
MATCH_FOUND
```

## Question

```text
QUESTION_STARTED
        ↓
┌───────┴────────┐
│                │
Player A       Player B
│                │
answer          answer
└───────┬────────┘
        ↓
Server evaluates
        ↓
QUESTION_RESULT
        ↓
Next question
```

## Completion

```text
MATCH_COMPLETED
       ↓
Calculate result
       ↓
Update ranking
       ↓
Check achievements
       ↓
Send final result
       ↓
Return players to global pool
```

---

# Service Layer

Keep game logic out of WebSocket consumers.

`apps/match/services.py`:

```python
enter_matchmaking(player)

leave_matchmaking(player)

create_matchup(player_a, player_b)

select_match_questions(matchup)

start_matchup(matchup)

start_question(matchup)

submit_answer(matchup, player, answer)

complete_question(matchup)

complete_matchup(matchup)

return_player_to_matchmaking(player)
```

The consumer should mainly:

```text
Receive event
    ↓
Validate
    ↓
Call service
    ↓
Send / broadcast event
```

This makes the game logic testable without requiring a live WebSocket connection.

---

# Question Selection & Evaluation

The `questions` app should own question selection.

```python
get_available_questions(
    category=category,
    tags=tags,
    level_range=(1, 10),
)
```

```python
select_questions(
    category=category,
    count=question_count,
)
```

Question evaluation should also remain in the questions domain.

Conceptual evaluators:

```text
SingleAnswerEvaluator
MultipleAnswerEvaluator
TrueFalseEvaluator
FreeTextEvaluator
OrderingEvaluator
MatrixEvaluator
```

Example:

```python
result = evaluate_answer(
    question=question,
    submitted_answer=answer,
)
```

Returns:

```json
{
  "is_correct": true,
  "score": 100
}
```

---

# Server-Authoritative Timing

The client displays the timer.

The server determines the actual response time.

```text
QUESTION_STARTED
server timestamp = T0

PLAYER_ANSWER
server receives = T1

response_time = T1 - T0
```

The client submits the answer only.

Do not trust client-submitted timing.

---

# Rankings

Rankings should be category-specific.

```python
class Ranking(models.Model):
    player = models.ForeignKey(
        "player.Player",
        on_delete=models.CASCADE,
        related_name="rankings",
    )

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.PROTECT,
        related_name="rankings",
    )

    rating = models.IntegerField(default=1000)

    wins = models.PositiveIntegerField(default=0)

    losses = models.PositiveIntegerField(default=0)

    games_played = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)
```

This allows:

```text
NBA Rating: 1482
F1 Rating: 1290
Premier League Rating: 1375
```

when additional categories are added.

---

# Achievements

Achievements remain separate from rankings.

```python
class Achievement(models.Model):
    name = models.CharField(max_length=100)

    slug = models.SlugField(unique=True)

    description = models.TextField()

    icon = models.ImageField(
        upload_to="achievements/",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
```

```python
class PlayerAchievement(models.Model):
    player = models.ForeignKey(
        "player.Player",
        on_delete=models.CASCADE,
        related_name="achievements",
    )

    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="players",
    )

    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "achievement"],
                name="unique_player_achievement",
            ),
        ]
```

Initial achievements:

```text
First Win
5 Wins
10 Wins
5 Win Streak
Perfect Match
100 Questions Answered
Fastest Answer
Beat a Higher Rated Player
```

---

# Initial MVP

## Account

```text
Authentication
Player creation
Display name
```

## Category

```text
NBA
```

## Questions

Start with:

```text
Single answer
True / False
Free text
Image answers
```

Then add:

```text
Ordering
Columns / Rows
```

## Match

```text
Global matchmaking
Random opponent
Random 3 / 5 / 7 questions
Same question for both players
Server-side timing
Server-side validation
Winner / loser
Return to matchmaking
```

## Ranking

```text
NBA rating
Wins
Losses
Games played
```

## Achievements

```text
First win
Win streak
Perfect match
Question milestones
```

---

# Core Product Loop

```text
OPEN APP
    ↓
ONLINE
    ↓
FIND OPPONENT
    ↓
GLOBAL MATCHMAKING
    ↓
OPPONENT FOUND
    ↓
RANDOM 3 / 5 / 7 QUESTIONS
    ↓
SAME QUESTION TO BOTH PLAYERS
    ↓
ANSWER AS FAST AS POSSIBLE
    ↓
SERVER VALIDATES
    ↓
QUESTION RESULT
    ↓
NEXT QUESTION
    ↓
MATCH COMPLETE
    ↓
WIN / LOSE
    ↓
RATING UPDATE
    ↓
ACHIEVEMENT CHECK
    ↓
PLAY AGAIN
    ↓
GLOBAL MATCHMAKING
```

# Core Architectural Rule

> **Redis + Django Channels manage who is online and what is happening right now. PostgreSQL stores what happened.**

The global pool is a realtime matchmaking mechanism, not a persistent database room.

The question architecture is independent from categories.

The match system is independent from the concrete question type.

This allows the same game engine to eventually power:

```text
NBA Rival
Premier League Rival
F1 Rival
UFC Rival
NFL Rival
...
```

