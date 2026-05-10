# Code Review & Audit: `projectsite/settings.py`

> Full audit of the 312-line `settings.py` file covering security, configuration, and best practices.

---

## 1. 🔒 Security

### 📍 Hardcoded database credentials
- **⚠️ Issue**: Lines 149-158 — Database credentials are hardcoded in the file:
  - `USER`: `postgres`
  - `PASSWORD`: `admin`
  - `HOST`: `localhost`
  - `PORT`: `5432`
- **✅ Suggestion**: Move to environment variables:
  ```python
  DATABASES = {
      'default': {
          'ENGINE': 'django.db.backends.postgresql',
          'NAME': config('DB_NAME', default='reals_local'),
          'USER': config('DB_USER', default='postgres'),
          'PASSWORD': config('DB_PASSWORD', default=''),
          'HOST': config('DB_HOST', default='localhost'),
          'PORT': config('DB_PORT', default='5432'),
      }
  }
  ```

### 📍 Hardcoded email credentials
- **⚠️ Issue**: Lines 302-306 — Email credentials are hardcoded:
  - `EMAIL_HOST`: `smtp.gmail.com`
  - `EMAIL_HOST_USER`: `inventcaps@gmail.com`
  - `EMAIL_HOST_PASSWORD`: default empty string
- **✅ Suggestion**: Move to environment variables:
  ```python
  EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
  EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
  EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
  EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
  EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
  ```

### 📍 DEBUG defaults to True
- **⚠️ Issue**: Line 16 — `DEBUG = config('DEBUG', default=True, cast=bool)` defaults to True. If the environment variable is missing, the app runs in debug mode in production.
- **✅ Suggestion**: Change default to `False`:
  ```python
  DEBUG = config('DEBUG', default=False, cast=bool)
  ```

### 📍 SECRET_KEY has insecure default
- **⚠️ Issue**: Line 13 — `SECRET_KEY` has a default value `django-insecure-hf7!w=oxut=ipo$@r0r&8^h1j^lg4-j2++qmgx)!ulm=!-$afb`. If the environment variable is missing, this insecure key is used.
- **✅ Suggestion**: Remove the default or raise an error if missing:
  ```python
  SECRET_KEY = config('SECRET_KEY')
  # Or use a more secure approach for local dev:
  # SECRET_KEY = config('SECRET_KEY', default=None)
  # if not SECRET_KEY:
  #     raise ValueError("SECRET_KEY must be set in environment variables")
  ```

### 📍 ALLOWED_HOSTS includes wildcard
- **⚠️ Issue**: Line 18 — `ALLOWED_HOSTS` default includes `*` which allows any host. This is dangerous in production.
- **✅ Suggestion**: Remove `*` from default:
  ```python
  ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
  ```

### 📍 SECURE_SSL_REDIRECT defaults to False
- **⚠️ Issue**: Line 24 — `SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)` defaults to False. Production should enforce HTTPS.
- **✅ Suggestion**: Set to True in production or use environment-based default:
  ```python
  SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
  ```

### 📍 SESSION_COOKIE_SECURE defaults to False
- **⚠️ Issue**: Line 28 — `SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)` defaults to False. Sessions can be sent over HTTP.
- **✅ Suggestion**: Set to True in production:
  ```python
  SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
  ```

### 📍 SECURE_HSTS_SECONDS defaults to 0
- **⚠️ Issue**: Line 31 — `SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)` defaults to 0, disabling HSTS. Production should have HSTS enabled.
- **✅ Suggestion**: Set a reasonable default for production:
  ```python
  SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000 if not DEBUG else 0, cast=int)
  ```

### 📍 CSRF_COOKIE_SECURE defaults to True but SESSION_COOKIE_SECURE defaults to False
- **⚠️ Issue**: Lines 20, 28 — Inconsistent security defaults. CSRF cookies are secure by default but session cookies are not.
- **✅ Suggestion**: Make both consistent:
  ```python
  CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)
  SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
  ```

### 📍 SENDGRID_API_KEY has empty default
- **⚠️ Issue**: Line 289 — `SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')` has empty default. Production emails will fail silently if the key is missing.
- **✅ Suggestion**: Raise error if missing in production:
  ```python
  SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')
  if not DEBUG and not SENDGRID_API_KEY:
      raise ValueError("SENDGRID_API_KEY must be set in production")
  ```

### 📍 InMemoryChannelLayer in production
- **⚠️ Issue**: Lines 53-57 — `CHANNEL_LAYERS` uses `InMemoryChannelLayer` which is not suitable for production (doesn't work with multiple workers/processes).
- **✅ Suggestion**: Use Redis in production:
  ```python
  CHANNEL_LAYERS = {
      "default": {
          "BACKEND": "channels_redis.core.RedisChannelLayer",
                          "CONFIG": {
                              "hosts": [config('REDIS_URL', default='redis://localhost:6379')],
                          },
                      }
                  } if not DEBUG else {
                      "BACKEND": "channels.layers.InMemoryChannelLayer"
                  }
  }
  ```

### 📍 LocMemCache in production
- **⚠️ Issue**: Lines 225-235 — `CACHES` uses `LocMemCache` which is not suitable for production (doesn't work with multiple workers/processes, data lost on restart).
- **✅ Suggestion**: Use Redis or Memcached in production:
  ```python
  CACHES = {
      'default': {
          'BACKEND': 'django.core.cache.backends.redis.RedisCache',
          'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
      }
  } if not DEBUG else {
      'default': {
          'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
          'LOCATION': 'reals-inventory-cache',
      }
  }
  ```

### 📍 No rate limiting configuration
- **⚠️ Issue**: No rate limiting middleware or settings configured. Vulnerable to brute force attacks on login, password reset, etc.
- **✅ Suggestion**: Add django-ratelimit or similar:
  ```python
  INSTALLED_APPS = [
      ...
      'django_ratelimit',
  ]
  MIDDLEWARE = [
      ...
      'django_ratelimit.middleware.RatelimitMiddleware',
  ]
  ```

### 📍 No X-Frame-Options DENY
- **⚠️ Issue**: Django's default `XFrameOptionsMiddleware` is present (line 67) but uses `SAMEORIGIN`. For sensitive apps, `DENY` is more secure.
- **✅ Suggestion**: Add:
  ```python
  X_FRAME_OPTIONS = 'DENY'
  ```

### 📍 No Content-Security-Policy
- **⚠️ Issue**: No CSP headers configured. Vulnerable to XSS attacks.
- **✅ Suggestion**: Add django-csp or middleware:
  ```python
  SECURE_CONTENT_SECURITY_POLICY = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
  ```

### 📍 No SECURE_BROWSER_XSS_FILTER
- **⚠️ Issue**: Not set. Should be enabled for production.
- **✅ Suggestion**: Add:
  ```python
  SECURE_BROWSER_XSS_FILTER = True
  ```

### 📍 No SECURE_REFERRER_POLICY
- **⚠️ Issue**: Not set. Should be configured for production.
- **✅ Suggestion**: Add:
  ```python
  SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
  ```

---

## 2. 🏗️ Structure & Best Practices

### 📍 Massive commented-out database configurations
- **⚠️ Issue**: Lines 97-147 — 50+ lines of commented-out database configurations. This makes the file hard to read and maintain.
- **✅ Suggestion**: Remove all commented-out configurations. Keep only the active one. Use version control for history.

### 📍 Duplicate import of `os`
- **⚠️ Issue**: Line 2 and line 97 — `import os` is imported twice.
- **✅ Suggestion**: Remove line 97.

### 📍 Commented-out import
- **⚠️ Issue**: Line 4 — `# import dj_database_url` is commented out but the import is not used anyway.
- **✅ Suggestion**: Remove this line.

### 📍 Inconsistent comment style
- **⚠️ Issue**: Some comments use `#` at start of line, some inline. Inconsistent spacing after `#`.
- **✅ Suggestion**: Standardize on one style (PEP 8: `# comment` with space after `#`).

### 📍 Hardcoded backup directory
- **⚠️ Issue**: Line 237 — `BACKUP_DIR = os.path.join(BASE_DIR, 'backups')` is hardcoded. Should be configurable.
- **✅ Suggestion**: Move to environment variable:
  ```python
  BACKUP_DIR = config('BACKUP_DIR', default=os.path.join(BASE_DIR, 'backups'))
  ```

### 📍 Hardcoded backup retention
- **⚠️ Issue**: Line 238 — `BACKUP_KEEP_DAYS = 7` is hardcoded. Should be configurable.
- **✅ Suggestion**: Move to environment variable:
  ```python
  BACKUP_KEEP_DAYS = config('BACKUP_KEEP_DAYS', default=7, cast=int)
  ```

### 📍 Hardcoded upload limits
- **⚠️ Issue**: Lines 240-241 — `DATA_UPLOAD_MAX_MEMORY_SIZE` and `FILE_UPLOAD_MAX_MEMORY_SIZE` are hardcoded at 10MB.
- **✅ Suggestion**: Make configurable:
  ```python
  DATA_UPLOAD_MAX_MEMORY_SIZE = config('DATA_UPLOAD_MAX_MEMORY_SIZE', default=10485760, cast=int)
  FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=10485760, cast=int)
  ```

### 📍 No environment-specific settings file
- **⚠️ Issue**: All settings are in one file. No separation between development, staging, and production settings.
- **✅ Suggestion**: Use Django's pattern:
  ```python
  # settings/
  #   __init__.py
  #   base.py
  #   development.py
  #   production.py
  ```
  Or use `DJANGO_SETTINGS_MODULE` environment variable to switch.

### 📍 No logging to file in production
- **⚠️ Issue**: Lines 244-257 — Production logging only goes to console. No persistent log storage for debugging production issues.
- **✅ Suggestion**: Add file logging in production or use a logging service (Sentry, Loggly, etc.):
  ```python
  if not DEBUG:
      LOGGING = {
          'version': 1,
          'disable_existing_loggers': False,
          'handlers': {
              'console': {
                  'class': 'logging.StreamHandler',
              },
              'file': {
                  'class': 'logging.handlers.RotatingFileHandler',
                  'filename': '/var/log/django/app.log',
                  'maxBytes': 1024*1024*10,  # 10MB
                  'backupCount': 5,
              },
          },
          'root': {
              'handlers': ['console', 'file'],
          },
      }
  ```

### 📍 No Sentry or error tracking
- **⚠️ Issue**: No error tracking service configured. Production errors may go unnoticed.
- **✅ Suggestion**: Add Sentry:
  ```python
  import sentry_sdk
  from sentry_sdk.integrations.django import DjangoIntegration

  sentry_sdk.init(
      dsn=config('SENTRY_DSN', default=''),
      integrations=[DjangoIntegration()],
      traces_sample_rate=0.1,
  )
  ```

### 📍 Email backend logic is convoluted
- **⚠️ Issue**: Lines 291-299 — Nested if-else logic for email backend is hard to follow.
- **✅ Suggestion**: Simplify:
  ```python
  EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
  if not DEBUG and SENDGRID_API_KEY:
      EMAIL_BACKEND = 'realsproj.backends.SendGridBackend'
  DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='inventcaps@gmail.com')
  ```

### 📍 No connection pooling for database
- **⚠️ Issue**: No `CONN_MAX_AGE` set. Every request opens a new database connection.
- **✅ Suggestion**: Add connection pooling:
  ```python
  DATABASES = {
      'default': {
          ...
          'CONN_MAX_AGE': 600,  # 10 minutes
      }
  }
  ```

### 📍 No database health check
- **⚠️ Issue**: No health check endpoint configured for monitoring.
- **✅ Suggestion**: Add django-health-check or similar.

### 📍 No CORS configuration
- **⚠️ Issue**: If the app has a frontend separate from the backend, CORS is not configured.
- **✅ Suggestion**: Add django-cors-headers if needed:
  ```python
  INSTALLED_APPS = [
      ...
      'corsheaders',
  ]
  MIDDLEWARE = [
      'corsheaders.middleware.CorsMiddleware',
      ...
  ]
  CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000', cast=Csv())
  ```

---

## 3. 📝 Code Cleanliness

### 📍 Unused `SESSION_CACHE_ALIAS`
- **⚠️ Issue**: Line 221 — `SESSION_CACHE_ALIAS = 'default'` is set but `SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'` may not use it correctly without proper cache configuration.
- **✅ Suggestion**: Verify cache backend supports session storage or use `'django.contrib.sessions.backends.cache'` instead.

### 📍 Inconsistent use of `config()` defaults
- **⚠️ Issue**: Some settings use `config()` with defaults, others are hardcoded. Inconsistent approach.
- **✅ Suggestion**: Make all sensitive/variable settings use `config()` with appropriate defaults.

### 📍 Magic numbers
- **⚠️ Issue**: Lines 222, 230-231, 233, 240-241, 309 — Magic numbers like `86400`, `2000`, `3`, `300`, `10485760`, `30` without comments explaining their meaning.
- **✅ Suggestion**: Add comments or use named constants:
  ```python
  SESSION_COOKIE_AGE = 86400  # 24 hours in seconds
  ```

### 📍 No type hints for custom settings
- **⚠️ Issue**: Custom settings like `BACKUP_DIR`, `BACKUP_KEEP_DAYS` have no type hints or documentation.
- **✅ Suggestion**: Add docstrings or type hints for clarity.

---

## 4. 🔌 Configuration Issues

### 📍 Default email backend is console in production
- **⚠️ Issue**: Line 291 — `EMAIL_BACKEND` defaults to console backend even in production (the condition checks `if DEBUG and EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'`).
- **✅ Suggestion**: Fix the logic:
  ```python
  EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend' if DEBUG else 'realsproj.backends.SendGridBackend')
  ```

### 📍 Session engine mismatch with cache backend
- **⚠️ Issue**: Line 220 — `SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'` uses cache-backed sessions, but the cache is `LocMemCache` which loses data on restart.
- **✅ Suggestion**: Either use database sessions or Redis cache in production:
  ```python
  SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # More reliable
  # Or use Redis cache in production
  ```

### 📍 No email server timeout validation
- **⚠️ Issue**: Line 309 — `EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=30, cast=int)` has a default but no validation that it's reasonable.
- **✅ Suggestion**: Add validation:
  ```python
  EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=30, cast=int)
  if EMAIL_TIMEOUT < 5 or EMAIL_TIMEOUT > 120:
      raise ValueError("EMAIL_TIMEOUT must be between 5 and 120 seconds")
  ```

### 📍 No validation for upload limits
- **⚠️ Issue**: Lines 240-241 — No validation that upload limits are reasonable.
- **✅ Suggestion**: Add validation or use Django's default.

---

## Summary Statistics

| Category | Issues Found |
|---|---|
| 🔒 Security | 16 |
| 🏗️ Structure & Best Practices | 14 |
| 📝 Code Cleanliness | 4 |
| 🔌 Configuration Issues | 4 |
| **Total** | **38** |

---

## 🔥 Top Priority Fixes

1. **Move database credentials to environment variables** — Security (lines 149-158)
2. **Move email credentials to environment variables** — Security (lines 302-306)
3. **Change DEBUG default to False** — Security (line 16)
4. **Remove SECRET_KEY default or raise error if missing** — Security (line 13)
5. **Remove `*` from ALLOWED_HOSTS default** — Security (line 18)
6. **Set SECURE_SSL_REDIRECT based on DEBUG** — Security (line 24)
7. **Set SESSION_COOKIE_SECURE based on DEBUG** — Security (line 28)
8. **Use Redis for CHANNEL_LAYERS in production** — Security (lines 53-57)
9. **Use Redis for CACHES in production** — Security (lines 225-235)
10. **Remove 50+ lines of commented-out database configs** — Structure (lines 97-147)
