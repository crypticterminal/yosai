import pytest
from yosai.core import (
    AdditionalAuthenticationRequired,
    AuthenticationException,
    InvalidAuthenticationSequenceException,
    LockedAccountException,
    SerializationManager,
    SimpleIdentifierCollection,
    UsernamePasswordToken,
    AuthenticationException,
)


def test_single_factor_authc_userpass_using_accountstore_success(
        caplog, default_authenticator, valid_walter_username_password_token,
        event_bus, cache_handler):
    da = default_authenticator
    event_detected = None

    def event_listener(identifier=None):
        nonlocal event_detected
        event_detected = identifier
    event_bus.register(event_listener, 'AUTHENTICATION.SUCCEEDED')

    account_id = da.authenticate_account(None, valid_walter_username_password_token)
    out = caplog.text
    assert (event_detected == account_id.primary_identifier and
            ("Could not obtain cached" in out and "No account" not in out))


def test_multi_factor_authc_raises_invalid_sequence(
        default_authenticator, valid_thedude_totp_token):
    da = default_authenticator

    with pytest.raises(InvalidAuthenticationSequenceException):
        da.authenticate_account(None, valid_thedude_totp_token)


def test_multi_factor_authc_using_accountstore_success(
        caplog, default_authenticator, valid_thedude_username_password_token,
        valid_thedude_totp_token, event_bus):
    da = default_authenticator
    success_event_detected = None
    progress_event_detected = None

    def progress_event_listener(identifier=None):
        nonlocal progress_event_detected
        progress_event_detected = identifier
    event_bus.register(progress_event_listener, 'AUTHENTICATION.PROGRESS')

    def success_event_listener(identifier=None):
        nonlocal success_event_detected
        success_event_detected = identifier
    event_bus.register(success_event_listener, 'AUTHENTICATION.SUCCEEDED')

    try:
        account_id = da.authenticate_account(None, valid_thedude_username_password_token)
    except AdditionalAuthenticationRequired as exc:
        account_id = da.authenticate_account(exc.account_id, valid_thedude_totp_token)

    out = caplog.text
    assert (success_event_detected == account_id.primary_identifier and
            progress_event_detected == account_id.primary_identifier and
            ("Could not obtain cached" in out and "No account" not in out))


def test_single_factor_authc_userpass_using_cache_success(
        caplog, default_authenticator, valid_walter_username_password_token,
        invalid_walter_username_password_token, event_bus):

    da = default_authenticator
    event_detected = None

    def event_listener(identifier=None):
        nonlocal event_detected
        event_detected = identifier
    event_bus.register(event_listener, 'AUTHENTICATION.SUCCEEDED')

    try:
        # first authentication fails, intentionally, but caches results
        da.authenticate_account(None, invalid_walter_username_password_token)
    except AuthenticationException:
        account_id = da.authenticate_account(None, valid_walter_username_password_token)

        out = caplog.text
        assert (event_detected == account_id.primary_identifier and
               "Could not obtain cached" in out and
                account_id.primary_identifier == valid_walter_username_password_token.identifier)


def test_single_factor_authc_userpass_using_accountstore_failure(
        caplog, default_authenticator, invalid_walter_username_password_token,
        event_bus):

    da = default_authenticator
    event_detected = None

    def event_listener(identifier=None):
        nonlocal event_detected
        event_detected = identifier
    event_bus.register(event_listener, 'AUTHENTICATION.FAILED')

    with pytest.raises(AuthenticationException):
        account_id = da.authenticate_account(None, invalid_walter_username_password_token)

        out = caplog.text
        assert (event_detected == account_id.primary_identifier and
                ("Could not obtain cached" in out and "No account" not in out))


def test_single_factor_authc_userpass_using_cache_failure(
        caplog, default_authenticator, invalid_thedude_username_password_token,
        cache_handler, event_bus):

    da = default_authenticator
    event_detected = None

    def event_listener(identifier=None):
        nonlocal event_detected
        event_detected = identifier
    event_bus.register(event_listener, 'AUTHENTICATION.FAILED')

    cred = 'letsgobowlingggggg'
    cache_handler.set(domain='credentials', identifier='thedude', value=cred)

    with pytest.raises(AuthenticationException):
        da.authenticate_account(None, invalid_thedude_username_password_token)
        out = caplog.text

        assert (event_detected == invalid_thedude_username_password_token.identifier and
                ("Could not obtain cached" not in out))

    cache_handler.delete(domain='credentials', identifier='thedude')

def test_single_factor_authc_userpass_using_accountstore_user_not_found(
        default_authenticator, event_bus):
    da = default_authenticator
    event_detected = None

    def event_listener(identifier=None):
        nonlocal event_detected
        event_detected = identifier
    event_bus.register(event_listener, 'AUTHENTICATION.ACCOUNT_NOT_FOUND')

    dumb_token = UsernamePasswordToken(username='dumb',
                                       password='token',
                                       remember_me=False,
                                       host='127.0.0.1')

    with pytest.raises(AuthenticationException):
        da.authenticate_account(None, dumb_token)

    assert (event_detected == dumb_token.identifier)


def test_single_factor_locks_account(
        default_authenticator, invalid_walter_username_password_token,
        event_bus, monkeypatch, valid_walter_username_password_token):
    """
        - locks a single-factor account after N attempts
        - confirms that a locked account will not authenticate userpass
    """
    da = default_authenticator
    lock_event_detected = None
    fail_event_detected = None
    success_event_detected = None
    other_success_event_detected = None

    def lock_event_listener(identifier=None):
        nonlocal lock_event_detected
        lock_event_detected = identifier

    def fail_event_listener(identifier=None):
        nonlocal fail_event_detected
        fail_event_detected = identifier

    def success_event_listener(identifier=None):
        nonlocal success_event_detected
        success_event_detected = identifier

    def other_success_event_listener(identifier=None):
        nonlocal other_success_event_detected
        other_success_event_detected = identifier

    monkeypatch.setattr(da.authc_settings, 'account_lock_threshold', 3)
    da.init_locking()

    event_bus.register(success_event_listener, 'AUTHENTICATION.SUCCEEDED')

    da.locking_realm.unlock_account('walter')
    account_id = da.authenticate_account(None, valid_walter_username_password_token)
    assert success_event_detected == account_id.primary_identifier == 'walter'

    try:
        account_id = da.authenticate_account(None, invalid_walter_username_password_token)
    except AuthenticationException:
        try:
            account_id = da.authenticate_account(None, invalid_walter_username_password_token)
        except AuthenticationException:
            try:
                account_id = da.authenticate_account(None, invalid_walter_username_password_token)
            except AuthenticationException:
                try:
                    account_id = da.authenticate_account(None, invalid_walter_username_password_token)
                except LockedAccountException:
                    try:
                        event_bus.register(fail_event_listener, 'AUTHENTICATION.FAILED')
                        event_bus.register(lock_event_listener, 'AUTHENTICATION.ACCOUNT_LOCKED')
                        event_bus.register(other_success_event_listener, 'AUTHENTICATION.SUCCEEDED')
                        account_id = da.authenticate_account(None, valid_walter_username_password_token)
                    except LockedAccountException:
                        assert lock_event_detected == fail_event_detected == 'walter'
                        assert other_success_event_detected is None

#def test_multi_factor_locks_account
#    - locks an account after N attempts during totp authc
#    - confirms that a locked account will not authenticate totp
