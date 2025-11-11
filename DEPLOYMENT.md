# Deployment Guide - Render with Supabase

## Prerequisites
- GitHub account
- Render account (free tier available at https://render.com)
- Your code pushed to a GitHub repository
- Supabase database already configured ✅

## Step-by-Step Deployment

### 1. Push Your Code to GitHub
```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

### 2. Create a New Web Service on Render

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select your repository: `Inventory-and-Sales-Management-System-for-Reals-Food-Products`

### 3. Configure the Web Service

**Basic Settings:**
- **Name:** `reals-inventory-system` (or your preferred name)
- **Region:** Singapore (closest to Philippines)
- **Branch:** `main`
- **Root Directory:** Leave empty
- **Runtime:** `Python 3`
- **Build Command:** `./build.sh`
- **Start Command:** `daphne -b 0.0.0.0 -p $PORT projectsite.asgi:application`

### 4. Set Environment Variables

Click **"Advanced"** and add these environment variables:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | Generate a new one (click "Generate" button) |
| `DEBUG` | `False` |
| `PYTHON_VERSION` | `3.11.0` |
| `DATABASE_URL` | `postgresql://postgres:Reals_db_123@db.rczsumkmhoxjaycvggzt.supabase.co:5432/postgres` |

**Important:** After deployment, update these variables:
- `ALLOWED_HOSTS` - Add your Render URL (e.g., `reals-inventory-system.onrender.com`)
- `CSRF_TRUSTED_ORIGINS` - Add `https://reals-inventory-system.onrender.com`

### 5. Deploy

1. Click **"Create Web Service"**
2. Wait for the build to complete (5-10 minutes)
3. Your app will be live at: `https://your-service-name.onrender.com`

## Post-Deployment

### Update Settings After First Deploy

Once you get your Render URL (e.g., `reals-inventory-system.onrender.com`):

1. Go to **Environment** tab in Render dashboard
2. Update or add:
   - `ALLOWED_HOSTS` = `reals-inventory-system.onrender.com,localhost`
   - `CSRF_TRUSTED_ORIGINS` = `https://reals-inventory-system.onrender.com`
3. Click **"Save Changes"** (this will trigger a redeploy)

### Create Superuser (Admin Account)

1. In Render dashboard, go to your service
2. Click **"Shell"** tab
3. Run:
```bash
cd projectsite
python manage.py createsuperuser
```

## Important Notes

✅ **Supabase Database:** Your app will use your existing Supabase PostgreSQL database
✅ **WebSockets:** Supported via Daphne (ASGI server)
✅ **Static Files:** Handled by WhiteNoise
✅ **Free Tier:** Render free tier includes:
   - 750 hours/month
   - Automatic HTTPS
   - Sleeps after 15 minutes of inactivity

## Troubleshooting

### Build Fails
- Check the build logs in Render dashboard
- Ensure `build.sh` has execute permissions (should be automatic)

### Database Connection Issues
- Verify DATABASE_URL is correct
- Check Supabase dashboard for connection limits

### Static Files Not Loading
- Run `python manage.py collectstatic` in Shell
- Check STATIC_ROOT and STATICFILES_STORAGE settings

### App Sleeps (Free Tier)
- Free tier apps sleep after 15 minutes of inactivity
- First request after sleep takes ~30 seconds to wake up
- Upgrade to paid tier ($7/month) for always-on service

## Support

For issues, check:
- Render Logs: Dashboard → Logs tab
- Django Debug: Set DEBUG=True temporarily (remember to set back to False!)
