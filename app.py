from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_, or_
import os

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

    new_task = Task(
        title=title,
        status="Pending",
        due_date=due_date,
        priority=priority,
        tags=tags if tags else None
    )
    db.session.add(new_task)
    db.session.commit()
    flash(f"Added task: {title}", "success")
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>")
def toggle_task(task_id):
    task = Task.query.get(task_id)
    if task:
        task.status = "Completed" if task.status == "Pending" else "Pending"
        if task.status == "Completed":
            task.completed_at = now_utc()
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
    
    return jsonify({
        'completed_today': completed_today,
        'completed_week': completed_week,
        'overdue': overdue,
        'total_pending': total_pending,
        'total_completed': total_completed
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
