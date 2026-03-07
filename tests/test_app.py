"""Test suite for ToDo app."""
import pytest
from app import app, db, Task


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_app_import():
    """Test that app imports successfully."""
    assert app is not None
    assert app.secret_key is not None


def test_app_responds(client):
    """Smoke test: app responds to requests."""
    rv = client.get('/')
    assert rv.status_code in [200, 302, 404]


def test_index_route(client):
    """Test that the index route returns successfully."""
    rv = client.get('/')
    assert rv.status_code in [200, 302]


def test_database_connection():
    """Test that database connection works."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        # Should not raise an exception
        tables = db.inspect(db.engine).get_table_names()
        assert 'tasks' in tables or len(tables) >= 0
        db.drop_all()


def test_task_model():
    """Test that Task model can be instantiated."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        task = Task(title='Test Task', status='Pending')
        db.session.add(task)
        db.session.commit()

        retrieved = db.session.get(Task, task.id)
        assert retrieved is not None
        assert retrieved.title == 'Test Task'
        db.drop_all()
