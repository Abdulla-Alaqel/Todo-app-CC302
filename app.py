from flask import Flask, render_template, request, redirect, url_for, flash, session

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
    theme = session.get('theme', 'light')
    return render_template("index.html", tasks=tasks, theme=theme)


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


@app.route("/toggle_theme")
def toggle_theme():
    current_theme = session.get('theme', 'light')
    session['theme'] = 'dark' if current_theme == 'light' else 'light'
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
    theme = session.get('theme', 'light')
    return render_template('index.html', tasks=tasks, edit_task=task, theme=theme)


if __name__ == "__main__":
    app.run(debug=True)
