import json
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Project, ProjectMembership


# ===========================================================================
# BLOCK A — Authentication & Collaborators
# US-01 (I-AUTH-01), US-02 (I-AUTH-02), US-05 (I-COLL-01)
# ===========================================================================

class RegistrationTestCase(APITestCase):
    """
    US-01 — New user registration.
    Registration must create the account with the provided data,
    return 201, and leave the user authenticated immediately.
    """

    URL = '/api/v1/auth/register/'

    def test_a01_successful_registration_returns_201_and_user_data(self):
        """A-01: Valid registration creates the account and returns 201."""
        payload = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], 'newuser')
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_a01_user_is_authenticated_after_registration(self):
        """A-01: After registering, /auth/me/ returns the user without a separate login step."""
        payload = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
        }
        self.client.post(self.URL, payload, format='json')

        me_response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['user']['username'], 'newuser')

    def test_a01_registration_fails_when_required_fields_are_missing(self):
        """A-01 edge: Incomplete payload returns 400."""
        response = self.client.post(self.URL, {'username': 'incomplete'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a01_registration_fails_with_duplicate_username(self):
        """A-01 edge: Already-taken username returns 400."""
        User.objects.create_user(
            username='taken', email='taken@example.com', password='pass12345'
        )
        payload = {
            'username': 'taken',
            'email': 'other@example.com',
            'password': 'pass12345',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data.get('error', ''))

    def test_a01_registration_fails_with_duplicate_email(self):
        """A-01 edge: Already-registered email returns 400."""
        User.objects.create_user(
            username='user1', email='dup@example.com', password='pass12345'
        )
        payload = {
            'username': 'user2',
            'email': 'dup@example.com',
            'password': 'pass12345',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data.get('error', ''))


class AuthenticationTestCase(APITestCase):
    """
    US-02 — Login and logout.
    Login must validate credentials and open a session.
    Logout must close the session and block subsequent access.
    """

    LOGIN_URL = '/api/v1/auth/login/'
    LOGOUT_URL = '/api/v1/auth/logout/'
    ME_URL = '/api/v1/auth/me/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='correctpass123',
        )

    def test_a02_login_with_correct_credentials_returns_200(self):
        """A-02: Correct credentials return 200 and user data."""
        payload = {'username': 'testuser', 'password': 'correctpass123'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], 'testuser')

    def test_a03_login_with_wrong_password_returns_401(self):
        """A-03: Wrong password returns 401 with an error message."""
        payload = {'username': 'testuser', 'password': 'wrongpass'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.data)

    def test_a03_login_with_nonexistent_user_returns_401(self):
        """A-03 edge: Unknown username returns 401."""
        payload = {'username': 'nobody', 'password': 'whatever123'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a04_logout_of_authenticated_user_returns_200(self):
        """A-04: Successful logout returns 200 with confirmation."""
        self.client.force_login(self.user)

        response = self.client.post(self.LOGOUT_URL, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('detail'), 'logged out')

    def test_a04_me_endpoint_is_inaccessible_after_logout(self):
        """A-04: After logout, /auth/me/ returns 403."""
        self.client.force_login(self.user)
        self.client.post(self.LOGOUT_URL, format='json')

        me_response = self.client.get(self.ME_URL)

        self.assertEqual(me_response.status_code, status.HTTP_403_FORBIDDEN)


class CollaboratorManagementTestCase(APITestCase):
    """
    US-05 — Adding collaborators and role assignment.
    The owner can add members with a role.
    Trying to add someone already in the project warns without duplicating.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='ownerpass123'
        )
        self.collaborator = User.objects.create_user(
            username='collab', email='collab@example.com', password='collabpass123'
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='A test project',
            owner=self.owner,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        self.add_url = f'/api/v1/projects/{self.project.pk}/add_collaborator/'
        self.client.force_login(self.owner)

    def test_a05_owner_adds_collaborator_with_role(self):
        """A-05: Owner adds a new collaborator with role 'reviewer'."""
        payload = {'username': 'collab', 'role': 'reviewer'}
        response = self.client.post(self.add_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'collaborator added')
        self.assertEqual(response.data['collaborator']['role'], 'reviewer')
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.collaborator,
                role='reviewer',
            ).exists()
        )

    def test_a06_adding_existing_member_warns_and_does_not_duplicate(self):
        """A-06: Re-adding an existing member returns a warning and no duplicate membership is created."""
        ProjectMembership.objects.create(
            project=self.project, user=self.collaborator, role='reviewer')
        self.project.collaborators.add(self.collaborator)

        payload = {'username': 'collab', 'role': 'viewer'}
        response = self.client.post(self.add_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'collaborator updated')
        membership_count = ProjectMembership.objects.filter(
            project=self.project, user=self.collaborator
        ).count()
        self.assertEqual(membership_count, 1)