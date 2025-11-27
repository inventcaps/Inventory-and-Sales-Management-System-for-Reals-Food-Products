from pathlib import Path
import os
from decouple import config, Csv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-hf7!w=oxut=ipo$@r0r&8^h1j^lg4-j2++qmgx)!ulm=!-$afb')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*,localhost,127.0.0.1,.ngrok-free.app,.onrender.com,.railway.app', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://*.ngrok-free.app,https://*.onrender.com,https://*.railway.app,https://reals-food-inventory-production.up.railway.app', cast=Csv())
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_HTTPONLY = config('CSRF_COOKIE_HTTPONLY', default=False, cast=bool)

# WebSocket settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'realsproj',
    'widget_tweaks',
    'django.contrib.humanize',
    "channels",
]

ASGI_APPLICATION = "projectsite.asgi.application"

# Channels layer (Redis backend)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'realsproj.middleware.UpdateLastActivityMiddleware',
    'realsproj.middleware.SetCurrentUserMiddleware',  # Set current user for history logging
]

ROOT_URLCONF = 'projectsite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'realsproj.context_processors.notifications_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'projectsite.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Database configuration with fallback
import os
# DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.ynmwkydtjzqppyecqhux:Reals_DB_123@aws-1-us-east-1.pooler.supabase.com:6543/postgres')

# DATABASES = {
#     'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)
# }

# # Add SSL requirement for Supabase
# DATABASES['default']['OPTIONS'] = {
#     'sslmode': 'require',
# }

# Alternative local database configuration (commented out)
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'reals_local',
#         'USER': 'postgres',
#         'PASSWORD': 'root',
#         'HOST': 'localhost',
#         'PORT': '5432',
#     }
# }
#         'OPTIONS': {
#             'sslmode': 'require',
#         },
#     }
# }

# DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.postgresql',
#        'NAME': 'r_local',
#        'USER': 'postgres',
#        'PASSWORD': 'root',
#        'HOST': 'localhost',
#        'PORT': '5432',
#    }
# }

DATABASES = {
   'default': {
       'ENGINE': 'django.db.backends.postgresql',
       'NAME': 'reals_db_reals',
       'USER': 'postgres',
       'PASSWORD': 'admin',
       'HOST': 'localhost',
       'PORT': '5432',
   }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'realsproj.validators.ComplexPasswordValidator',
    },
]

# Password hashers - optimized for development speed
if DEBUG:
    # Fast hashing for development
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',  # Fast for dev
        'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    ]
else:
    # Secure hashing for production
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.PBKDF2PasswordHasher',
        'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
        'django.contrib.auth.hashers.ScryptPasswordHasher',
    ]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Manila'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_REDIRECT_URL = 'home' 
LOGIN_URL = 'login'

# Session optimization for faster login
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = False

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'reals-inventory-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 2000,
            'CULL_FREQUENCY': 3,
        },
        'TIMEOUT': 300,  
    }
}

BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
BACKUP_KEEP_DAYS = 7

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760 
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760 

# Simplified logging for Railway deployment
if not DEBUG:
    # Production: simple console logging only
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
        },
    }
else:
    # Development: keep file logging
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                'style': '{',
            },
            'simple': {
                'format': '{levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
            },
        },
        'root': {
            'handlers': ['console'],
        },
    }

# Email Configuration - Use SendGrid (HTTP API, bypasses Railway SMTP blocks)
SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')

if DEBUG:
    # Development: use console backend for testing
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'inventcaps@gmail.com'
else:
    # Production: use SendGrid HTTP API (works on Railway, doesn't use SMTP)
    if SENDGRID_API_KEY:
        EMAIL_BACKEND = 'realsproj.backends.SendGridBackend'
    else:
        # Fallback to console if no API key
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='inventcaps@gmail.com')

# Email timeout settings
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=30, cast=int)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'