from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_
import calendar

app = Flask(__name__)
app.secret_key = "dev-secret-key"

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


def now_utc():
    """Get current UTC time as timezone-aware datetime"""
    return datetime.now(timezone.utc)


# Models
class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Pending", index=True)
    due_date = db.Column(db.DateTime, nullable=True, index=True)
    priority = db.Column(db.String(50), nullable=False, default="Medium")  # Low, Medium, High
    tags = db.Column(db.String(255), nullable=True)  # Comma-separated
    recurrence_type = db.Column(db.String(20), nullable=True, default=None)
    recurrence_interval = db.Column(db.Integer, nullable=False, default=1)
    recurrence_days = db.Column(db.String(100), nullable=True)  # Comma-separated weekday names for weekly recurrence
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'status': self.status,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'priority': self.priority,
            'tags': self.tags,
            'recurrence_type': self.recurrence_type,
            'recurrence_interval': self.recurrence_interval,
            'recurrence_days': self.recurrence_days,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, nullable=True)  # Optional for now, can be used for user auth later
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc, index=True)

    # Relationship to task
    task = db.relationship('Task', backref=db.backref('comments', lazy=True, order_by='Comment.created_at'))

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'author_id': self.author_id,
            'body': self.body,
            'created_at': self.created_at.isoformat(),
        }


WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAY_NAME_TO_INT = {name: idx for idx, name in enumerate(WEEKDAY_NAMES)}


def normalize_recurrence_days(days):
    if not days:
        return None

    if isinstance(days, str):
        parts = [part.strip() for part in days.split(',') if part.strip()]
    else:
        parts = [part.strip() for part in days if part and part.strip()]

    normalized = []
    for part in parts:
        title = part.capitalize()
        if title in WEEKDAY_NAME_TO_INT:
            normalized.append(title)
        elif part.isdigit() and 0 <= int(part) <= 6:
            normalized.append(WEEKDAY_NAMES[int(part)])

    return ', '.join(dict.fromkeys(normalized)) if normalized else None


def next_month_date(current, interval):
    month = current.month - 1 + interval
    year = current.year + month // 12
    month = month % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return current.replace(year=year, month=month, day=day)


def calculate_next_due_date(current, recurrence_type, interval, recurrence_days):
    if recurrence_type not in ['daily', 'weekly', 'monthly'] or interval < 1:
        return None

    if not current:
        current = now_utc()

    if recurrence_type == 'daily':
        return current + timedelta(days=interval)

    if recurrence_type == 'weekly':
        day_names = normalize_recurrence_days(recurrence_days)
        weekdays = [WEEKDAY_NAME_TO_INT[name] for name in day_names.split(', ') if name] if day_names else []
        if not weekdays:
            return current + timedelta(weeks=interval)

        weekdays = sorted(set(weekdays))
        later_days = [d for d in weekdays if d > current.weekday()]
        if later_days:
            next_weekday = later_days[0]
            return current + timedelta(days=(next_weekday - current.weekday()))

        if current.weekday() in weekdays:
            weeks = interval
        else:
            weeks = 1

        first_weekday = weekdays[0]
        days_until_first = ((7 * weeks) - current.weekday() + first_weekday) % (7 * weeks)
        if days_until_first == 0:
            days_until_first = 7 * weeks
        return current + timedelta(days=days_until_first)

    if recurrence_type == 'monthly':
        return next_month_date(current, interval)

    return None


def compute_completion_streaks():
    completed_dates = sorted({
        completed.completed_at.date()
        for completed in Task.query.filter(
            and_(Task.status == "Completed", Task.completed_at.isnot(None))
        ).all()
    })

    if not completed_dates:
        return 0, 0

    best_streak = 0
    current_streak = 0
    streak = 0
    previous = None

    for date in completed_dates:
        if previous is None or date == previous + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        best_streak = max(best_streak, streak)
        previous = date

    today = now_utc().date()
    current_streak = 0
    check_day = today
    completed_set = set(completed_dates)
    while check_day in completed_set:
        current_streak += 1
        check_day -= timedelta(days=1)

    return current_streak, best_streak


def create_next_recurrence(task):
    if not task.recurrence_type:
        return None

    next_due = calculate_next_due_date(
        task.due_date or now_utc(),
        task.recurrence_type,
        task.recurrence_interval,
        task.recurrence_days
    )
    if not next_due:
        return None

    recurring_task = Task(
        title=task.title,
        status='Pending',
        due_date=next_due,
        priority=task.priority,
        tags=task.tags,
        recurrence_type=task.recurrence_type,
        recurrence_interval=task.recurrence_interval,
        recurrence_days=task.recurrence_days
    )
    db.session.add(recurring_task)
    return recurring_task


# Create database tables
with app.app_context():
    db.create_all()


@app.route("/", methods=["GET"])
def index():
    theme = session.get('theme', 'light')
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template("index.html", tasks=tasks, theme=theme)


@app.route("/add", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    due_date_str = request.form.get("due_date", "").strip()
    priority = request.form.get("priority", "Medium")
    tags = request.form.get("tags", "").strip()
    recurrence_type = request.form.get("recurrence_type", "").strip() or None
    recurrence_interval = request.form.get("recurrence_interval", "1").strip()
    recurrence_days = request.form.getlist("recurrence_days")

    if not title:
        flash("Task cannot be empty.", "warning")
        return redirect(url_for("index"))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.fromisoformat(due_date_str)
        except ValueError:
            flash("Invalid due date format.", "warning")
            return redirect(url_for("index"))

    try:
        recurrence_interval = max(1, int(recurrence_interval))
    except ValueError:
        recurrence_interval = 1

    recurrence_days = normalize_recurrence_days(recurrence_days)
    if recurrence_type != 'weekly':
        recurrence_days = None

    if recurrence_type not in ['daily', 'weekly', 'monthly']:
        recurrence_type = None
        recurrence_interval = 1
        recurrence_days = None

    new_task = Task(
        title=title,
        status="Pending",
        due_date=due_date,
        priority=priority,
        tags=tags if tags else None,
        recurrence_type=recurrence_type,
        recurrence_interval=recurrence_interval,
        recurrence_days=recurrence_days
    )
    db.session.add(new_task)
    db.session.commit()
    flash(f"Added task: {title}", "success")
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>")
def toggle_task(task_id):
    task = Task.query.get(task_id)
    if task:
        was_pending = task.status == "Pending"
        task.status = "Completed" if was_pending else "Pending"
        if task.status == "Completed":
            task.completed_at = now_utc()
            db.session.commit()
            if was_pending and task.recurrence_type:
                create_next_recurrence(task)
                db.session.commit()
        else:
            task.completed_at = None
            db.session.commit()
        flash(f"Toggled task: {task.title}", "info")
    else:
        flash(f"Task #{task_id} not found", "warning")
    return redirect(url_for("index"))


@app.route("/toggle_theme")
def toggle_theme():
    current_theme = session.get('theme', 'light')
    session['theme'] = 'dark' if current_theme == 'light' else 'light'
    return redirect(url_for("index"))


@app.route("/delete/<int:task_id>")
def delete_task(task_id):
    task = Task.query.get(task_id)
    if task:
        db.session.delete(task)
        db.session.commit()
        flash(f"Deleted task #{task_id}", "success")
    else:
        flash(f"Task #{task_id} not found", "warning")
    return redirect(url_for("index"))


@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        flash(f"Task #{task_id} not found", "warning")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        priority = request.form.get('priority', 'Medium')
        tags = request.form.get('tags', '').strip()
        due_date_str = request.form.get('due_date', '').strip()

        if not title:
            flash('Task title cannot be empty.', 'warning')
            return redirect(url_for('edit_task', task_id=task_id))

        task.title = title
        task.priority = priority
        task.tags = tags if tags else None
        recurrence_type = request.form.get('recurrence_type', '').strip() or None
        recurrence_interval = request.form.get('recurrence_interval', '1').strip()
        recurrence_days = request.form.getlist('recurrence_days')

        try:
            recurrence_interval = max(1, int(recurrence_interval))
        except ValueError:
            recurrence_interval = 1

        recurrence_days = normalize_recurrence_days(recurrence_days)
        if recurrence_type != 'weekly':
            recurrence_days = None

        if recurrence_type not in ['daily', 'weekly', 'monthly']:
            recurrence_type = None
            recurrence_interval = 1
            recurrence_days = None

        task.recurrence_type = recurrence_type
        task.recurrence_interval = recurrence_interval
        task.recurrence_days = recurrence_days

        if due_date_str:
            try:
                task.due_date = datetime.fromisoformat(due_date_str)
            except ValueError:
                flash("Invalid due date format.", "warning")
                return redirect(url_for('edit_task', task_id=task_id))
        else:
            task.due_date = None

        db.session.commit()
        flash(f"Updated task: {title}", 'success')
        return redirect(url_for('index'))

    # Render the main page but provide edit_task to show the edit form inline
    theme = session.get('theme', 'light')
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('index.html', tasks=tasks, edit_task=task, theme=theme)


# Comment endpoints
@app.route('/api/comments/<int:task_id>', methods=['GET'])
def get_comments(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    comments = Comment.query.filter_by(task_id=task_id).order_by(Comment.created_at).all()
    return jsonify([comment.to_dict() for comment in comments])


@app.route('/api/comments', methods=['POST'])
def create_comment():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    task_id = data.get('task_id')
    body = data.get('body', '').strip()

    if not task_id or not body:
        return jsonify({'error': 'Task ID and body are required'}), 400

    # Check if task exists
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Basic validation and sanitation
    if len(body) > 1000:  # Max length
        return jsonify({'error': 'Comment body too long (max 1000 characters)'}), 400

    # Create comment (author_id is optional and null for now)
    comment = Comment(
        task_id=task_id,
        author_id=data.get('author_id'),  # Optional
        body=body
    )

    db.session.add(comment)
    db.session.commit()

    return jsonify(comment.to_dict()), 201


@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    comment = Comment.query.get(comment_id)
    if not comment:
        return jsonify({'error': 'Comment not found'}), 404

    db.session.delete(comment)
    db.session.commit()

    return jsonify({'message': 'Comment deleted'}), 200


# Stats API Endpoints
@app.route('/api/stats/completed-today', methods=['GET'])
def stats_completed_today():
    today = now_utc().date()
    count = Task.query.filter(
        and_(
            Task.status == "Completed",
            func.date(Task.completed_at) == today
        )
    ).count()
    return jsonify({'count': count})


@app.route('/api/stats/completed-week', methods=['GET'])
def stats_completed_week():
    today = now_utc()
    week_ago = today - timedelta(days=7)
    count = Task.query.filter(
        and_(
            Task.status == "Completed",
            Task.completed_at >= week_ago
        )
    ).count()
    return jsonify({'count': count})


@app.route('/api/stats/overdue', methods=['GET'])
def stats_overdue():
    now = now_utc()
    count = Task.query.filter(
        and_(
            Task.status == "Pending",
            Task.due_date < now
        )
    ).count()
    return jsonify({'count': count})


@app.route('/api/stats/completion-trend', methods=['GET'])
def stats_completion_trend():
    days = request.args.get('days', default=7, type=int)
    if days not in [7, 14, 30]:
        days = 7

    now = now_utc()
    start_date = now - timedelta(days=days)

    # Get daily completion counts
    trend_data = db.session.query(
        func.date(Task.completed_at).label('date'),
        func.count(Task.id).label('count')
    ).filter(
        and_(
            Task.status == "Completed",
            Task.completed_at >= start_date
        )
    ).group_by(func.date(Task.completed_at)).all()

    result = {str(date): count for date, count in trend_data}
    return jsonify({'days': days, 'trend': result})


@app.route('/api/stats/by-priority', methods=['GET'])
def stats_by_priority():
    stats = db.session.query(
        Task.priority,
        func.count(Task.id).label('count')
    ).filter(Task.status == "Pending").group_by(Task.priority).all()

    result = {priority: count for priority, count in stats}
    return jsonify(result)


@app.route('/api/stats/by-tag', methods=['GET'])
def stats_by_tag():
    all_tasks = Task.query.filter(Task.status == "Pending").all()
    tag_counts = {}

    for task in all_tasks:
        if task.tags:
            for tag in task.tags.split(','):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return jsonify(tag_counts)


@app.route('/api/stats/summary', methods=['GET'])
def stats_summary():
    today = now_utc().date()
    now = now_utc()
    week_ago = now - timedelta(days=7)

    completed_today = Task.query.filter(
        and_(
            Task.status == "Completed",
            func.date(Task.completed_at) == today
        )
    ).count()

    completed_week = Task.query.filter(
        and_(
            Task.status == "Completed",
            Task.completed_at >= week_ago
        )
    ).count()

    overdue = Task.query.filter(
        and_(
            Task.status == "Pending",
            Task.due_date < now
        )
    ).count()

    total_pending = Task.query.filter(Task.status == "Pending").count()
    total_completed = Task.query.filter(Task.status == "Completed").count()
    current_streak, best_streak = compute_completion_streaks()

    return jsonify({
        'completed_today': completed_today,
        'completed_week': completed_week,
        'overdue': overdue,
        'total_pending': total_pending,
        'total_completed': total_completed,
        'current_streak': current_streak,
        'best_streak': best_streak
    })


# Bulk operations endpoint
@app.route('/api/bulk-update', methods=['POST'])
def bulk_update():
    """
    Handle bulk operations on multiple tasks.

    Expected JSON payload:
    {
        "task_ids": [1, 2, 3],
        "action": "complete" | "incomplete" | "priority" | "tags" | "delete",
        "data": {
            "priority": "High",  // For priority action
            "tags": "tag1, tag2",  // For tags action
            "tag_mode": "replace" | "append"  // For tags action
        }
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validate required fields
    task_ids = data.get('task_ids', [])
    action = data.get('action', '').strip().lower()
    action_data = data.get('data', {})

    # Validate task_ids
    if not task_ids or not isinstance(task_ids, list):
        return jsonify({'error': 'task_ids must be a non-empty list'}), 400

    if len(task_ids) > 100:
        return jsonify({'error': 'Cannot bulk update more than 100 tasks at once'}), 400

    # Validate action
    valid_actions = ['complete', 'incomplete', 'priority', 'tags', 'delete']
    if action not in valid_actions:
        return jsonify({'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'}), 400

    try:
        # Get all tasks
        tasks = Task.query.filter(Task.id.in_(task_ids)).all()

        # Validate all requested tasks exist
        found_ids = {task.id for task in tasks}
        missing_ids = set(task_ids) - found_ids

        if missing_ids:
            return jsonify({
                'error': f'Some tasks not found: {list(missing_ids)}',
                'missing_ids': list(missing_ids)
            }), 404

        # Perform the action
        if action == 'complete':
            for task in tasks:
                task.status = "Completed"
                task.completed_at = now_utc()
            message = f"Completed {len(tasks)} task(s)"

        elif action == 'incomplete':
            for task in tasks:
                task.status = "Pending"
                task.completed_at = None
            message = f"Marked {len(tasks)} task(s) as pending"

        elif action == 'priority':
            priority = action_data.get('priority', '').strip()
            if priority not in ['Low', 'Medium', 'High']:
                return jsonify({'error': 'Invalid priority. Must be Low, Medium, or High'}), 400

            for task in tasks:
                task.priority = priority
            message = f"Updated priority to '{priority}' for {len(tasks)} task(s)"

        elif action == 'tags':
            tags = action_data.get('tags', '').strip()
            tag_mode = action_data.get('tag_mode', 'replace').lower()

            if tag_mode not in ['replace', 'append']:
                return jsonify({'error': 'tag_mode must be "replace" or "append"'}), 400

            if not tags:
                return jsonify({'error': 'tags cannot be empty for tags action'}), 400

            for task in tasks:
                if tag_mode == 'replace':
                    task.tags = tags
                else:  # append
                    existing = task.tags.split(',') if task.tags else []
                    new_tags = [t.strip() for t in tags.split(',')]
                    combined = set(existing) | set(new_tags)
                    task.tags = ', '.join(sorted(combined))

            message = f"{tag_mode.capitalize()}ed tags to {len(tasks)} task(s)"

        elif action == 'delete':
            for task in tasks:
                db.session.delete(task)
            message = f"Deleted {len(tasks)} task(s)"

        db.session.commit()

        return jsonify({
            'success': True,
            'message': message,
            'updated_count': len(tasks)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error performing bulk operation: {str(e)}'}), 500


if __name__ == "__main__":
    app.run(debug=True)
