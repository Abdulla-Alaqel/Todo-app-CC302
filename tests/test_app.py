"""Test suite for ToDo app - CRUD Operations."""
import pytest
from app import app, db, Task


@pytest.fixture
def client():
    """Create a test client for the Flask app with in-memory database."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


# ============================================================================
# Baseline Tests
# ============================================================================

def test_app_import():
    """Test that app imports successfully."""
    assert app is not None
    assert app.secret_key is not None


def test_index_route_loads(client):
    """Test that the index route returns successfully."""
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'<!DOCTYPE html>' in rv.data or b'<html' in rv.data


# ============================================================================
# CREATE Tests
# ============================================================================

def test_create_task_basic(client):
    """Test creating a task via POST /add.

    AAA Pattern:
    - Arrange: Prepare form data
    - Act: POST to /add endpoint
    - Assert: Verify status and redirect
    """
# ARRANGE
    form_data = {"title": "Buy milk"}

    # ACT
    response = client.post("/add", data=form_data, follow_redirects=True)

    # ASSERT - Status code check
    assert response.status_code == 201
    assert b"Buy milk" in response.data


def test_create_task_with_priority_and_due_date(client):
    """Test creating a task with additional fields (priority, tags)."""
    # ARRANGE
    form_data = {
        "title": "Complete assignment",
        "priority": "High",
        "tags": "work,urgent"
    }

    # ACT
    response = client.post("/add", data=form_data, follow_redirects=True)

    # ASSERT - Status and content verification
    assert response.status_code == 200
    assert b"Complete assignment" in response.data
    assert b"High" in response.data


def test_create_multiple_tasks_and_verify_list(client):
    """Test creation of multiple tasks and verify they all appear in list.

    This test demonstrates READ/VERIFY step.
    """
# ARRANGE
    tasks_to_create = [
        {"title": "Task 1"},
        {"title": "Task 2"},
        {"title": "Task 3"}
    ]

    # ACT - Create tasks
    for task_data in tasks_to_create:
        response = client.post("/add", data=task_data, follow_redirects=True)
        assert response.status_code == 200

    # READ/VERIFY - Check all tasks appear in list
    list_response = client.get("/")
    assert response.status_code == 200
    assert b"Task 1" in list_response.data
    assert b"Task 2" in list_response.data
    assert b"Task 3" in list_response.data


def test_create_empty_task_fails(client):
    """Test that creating a task with empty title fails gracefully."""
    # ARRANGE
    form_data = {"title": ""}

    # ACT
    response = client.post("/add", data=form_data, follow_redirects=True)

    # ASSERT - Should redirect and show warning
    assert response.status_code == 200
    assert b"cannot be empty" in response.data or b"warning" in response.data


# ============================================================================
# UPDATE Tests
# ============================================================================

def test_update_task_title(client):
    """Test updating a task's title via POST /edit/<id>.

    AAA Pattern:
    - Arrange: Create a task, get its ID
    - Act: POST updated title to /edit/<id>
    - Assert: Verify updated content appears in list
    """
# ARRANGE - Create initial task
    create_response = client.post(
        "/add",
        data={"title": "Old title"},
        follow_redirects=True
    )
    assert b"Old title" in create_response.data

    # Get the task ID from database (within app context)
    with app.app_context():
        task = Task.query.filter_by(title="Old title").first()
        assert task is not None
        task_id = task.id

    # ACT - Update task
    update_data = {"title": "New title"}
    update_response = client.post(
        f"/edit/{task_id}",
        data=update_data,
        follow_redirects=True
    )

    # ASSERT
    assert update_response.status_code == 200
    # Verify new title appears in list
    assert b"New title" in update_response.data
    # Verify old title is gone
    assert b"Old title" not in update_response.data


def test_update_task_priority(client):
    """Test updating a task's priority."""
# ARRANGE
    client.post("/add", data={"title": "Test task", "priority": "Low"}, follow_redirects=True)

    with app.app_context():
        task = Task.query.filter_by(title="Test task").first()
        task_id = task.id

    # ACT
    update_response = client.post(
        f"/edit/{task_id}",
        data={"title": "Test task", "priority": "High"},
        follow_redirects=True
    )

    # ASSERT
    assert update_response.status_code == 200

    # Verify priority was updated in database
    with app.app_context():
        updated_task = Task.query.get(task_id)
        assert updated_task.priority == "High"


def test_update_nonexistent_task_fails(client):
    """Test that updating a non-existent task shows error."""
# ACT - Try to update task with ID that doesn't exist
    response = client.post(
        "/edit/999",
        data={"title": "Updated title"},
        follow_redirects=True
    )

    # ASSERT - Should show not found message
    assert response.status_code == 200
    assert b"not found" in response.data or b"warning" in response.data


# ============================================================================
# DELETE Tests
# ============================================================================

def test_delete_task(client):
    """Test deleting a task via GET /delete/<id>.

    AAA Pattern:
    - Arrange: Create a task
    - Act: GET /delete/<id>
    - Assert: Verify task no longer appears in list
    """
# ARRANGE - Create a task
    create_response = client.post(
        "/add",
        data={"title": "To be deleted"},
        follow_redirects=True
    )
    assert b"To be deleted" in create_response.data

    with app.app_context():
        task = Task.query.filter_by(title="To be deleted").first()
        assert task is not None
        task_id = task.id

    # ACT - Delete the task
    delete_response = client.get(f"/delete/{task_id}", follow_redirects=True)

    # ASSERT - Verify deletion
    assert delete_response.status_code == 200
    # Task should not appear in list anymore
    assert b"To be deleted" not in delete_response.data

    # Double-check in database
    with app.app_context():
        deleted_task = Task.query.get(task_id)
        assert deleted_task is None


def test_delete_task_leaves_others_intact(client):
    """Test that deleting one task doesn't affect others."""
# ARRANGE - Create multiple tasks
    client.post("/add", data={"title": "Keep this"}, follow_redirects=True)
    client.post("/add", data={"title": "Delete this"}, follow_redirects=True)
    client.post("/add", data={"title": "Keep this too"}, follow_redirects=True)

    with app.app_context():
        task_to_delete = Task.query.filter_by(title="Delete this").first()
        task_id = task_to_delete.id

    # ACT - Delete one specific task
    delete_response = client.get(f"/delete/{task_id}", follow_redirects=True)

    # ASSERT
    assert delete_response.status_code == 200
    assert b"Delete this" not in delete_response.data
    assert b"Keep this" in delete_response.data
    assert b"Keep this too" in delete_response.data


def test_delete_nonexistent_task_fails_gracefully(client):
    """Test that deleting a non-existent task shows error."""
    # ACT - Try to delete task with ID that doesn't exist
    response = client.get("/delete/999", follow_redirects=True)

    # ASSERT - Should show error/warning message
    assert response.status_code == 200
    assert b"not found" in response.data or b"warning" in response.data
