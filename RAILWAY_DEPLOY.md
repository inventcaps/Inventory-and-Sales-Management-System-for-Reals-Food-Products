# Railway Deployment Guide - MABILIS!

## Step 1: Push to GitHub (5 minutes)

```bash
git add .
git commit -m "Add Railway deployment config"
git push origin main
```

## Step 2: Deploy sa Railway (10 minutes)

### A. Sign Up / Login
1. Go to: https://railway.app
2. Click **"Login"** → **"Login with GitHub"**
3. Authorize Railway

### B. Create New Project
1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose: `Inventory-and-Sales-Management-System-for-Reals-Food-Products`
4. Click **"Deploy Now"**

### C. Add Environment Variables
1. Click your service → **"Variables"** tab
2. Click **"+ New Variable"** and add:

```
SECRET_KEY=django-insecure-hf7!w=oxut=ipo$@r0r&8^h1j^lg4-j2++qmgx)!ulm=!-$afb
DEBUG=False
DATABASE_URL=postgresql://postgres:Reals_db_123@db.rczsumkmhoxjaycvggzt.supabase.co:5432/postgres
ALLOWED_HOSTS=.railway.app,localhost
CSRF_TRUSTED_ORIGINS=https://*.railway.app
```

3. Click **"Add"** for each variable

### D. Generate Domain
1. Go to **"Settings"** tab
2. Scroll to **"Networking"**
3. Click **"Generate Domain"**
4. Copy your URL (e.g., `your-app.up.railway.app`)

### E. Run Migrations
1. Click **"Deployments"** tab
2. Wait for build to finish (green checkmark)
3. Click your service → **"Settings"** → **"Deploy"**
4. Or use Railway CLI:
   ```bash
   railway run python projectsite/manage.py migrate
   ```

## Step 3: Create Superuser

Option 1 - Railway Dashboard:
1. Go to your service
2. Click **"Settings"** → **"Deploy"** → **"Run Command"**
3. Enter: `python projectsite/manage.py createsuperuser`

Option 2 - Railway CLI:
```bash
railway login
railway link
railway run python projectsite/manage.py createsuperuser
```

## Done! 🎉

Your app is live at: `https://your-app.up.railway.app`

## Railway Advantages
✅ **$5 free credit/month** (~500 hours)
✅ **No sleep time** - always on!
✅ **Works with Supabase** - no SSL issues
✅ **Automatic HTTPS**
✅ **Fast deployment** (5-10 minutes)
✅ **Easy to use**

## Troubleshooting

### If deployment fails:
1. Check logs in Railway dashboard
2. Make sure all environment variables are set
3. Verify DATABASE_URL is correct

### If database connection fails:
1. Check Supabase is running
2. Verify password in DATABASE_URL
3. Try adding `?sslmode=require` to DATABASE_URL

### If static files not loading:
```bash
railway run python projectsite/manage.py collectstatic --no-input
```
