from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "dev-secret-key"

# In-memory storage for tasks
# Each task is a dict: {"id": int, "title": str, "status": "Pending"|"Completed"}
tasks = []


def _next_id():
    if not tasks:
        return 1
    return max(t["id"] for t in tasks) + 1


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", tasks=tasks)


@app.route("/add", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Task cannot be empty.", "warning")
        return redirect(url_for("index"))

    new_task = {"id": _next_id(), "title": title, "status": "Pending"}
    tasks.append(new_task)
    flash(f"Added task: {title}", "success")
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>")
def toggle_task(task_id):
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "Completed" if t["status"] == "Pending" else "Pending"
            flash(f"Toggled task: {t['title']}", "info")
            break
    return redirect(url_for("index"))


@app.route("/delete/<int:task_id>")
def delete_task(task_id):
    global tasks
    before = len(tasks)
    tasks = [t for t in tasks if t["id"] != task_id]
    if len(tasks) < before:
        flash(f"Deleted task #{task_id}", "success")
    else:
        flash(f"Task #{task_id} not found", "warning")
    return redirect(url_for("index"))


@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    # Find the task
    task = next((t for t in tasks if t['id'] == task_id), None)
    if not task:
        flash(f"Task #{task_id} not found", "warning")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Task title cannot be empty.', 'warning')
            return redirect(url_for('edit_task', task_id=task_id))
        task['title'] = title
        flash(f"Updated task: {title}", 'success')
        return redirect(url_for('index'))

    # Render the main page but provide edit_task to show the edit form inline
    return render_template('index.html', tasks=tasks, edit_task=task)


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
