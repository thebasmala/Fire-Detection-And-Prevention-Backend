# How to Push Your Project to GitHub

## Step 1: Create a GitHub Repository

1. Go to https://github.com
2. Sign in (or create an account)
3. Click the **"+"** icon in the top right → **"New repository"**
4. Fill in:
   - **Repository name**: `fire-detection-backend` (or your preferred name)
   - **Description**: `🔥 FastAPI backend for fire detection and prevention system with MQTT integration, AI-powered fire location, real-time alerts, and hardware device management`
   - **Visibility**: Choose **Public** or **Private**
   - **DO NOT** check "Initialize with README" (we already have files)
5. Click **"Create repository"**

## Step 2: Initialize Git in Your Project

Open your terminal in the project directory and run:

```bash
# Initialize git repository
git init

# Add all files to git
git add .

# Create your first commit
git commit -m "Initial commit: Fire Detection and Prevention Backend"

# Add your GitHub repository as remote (replace with your actual repo URL)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Rename default branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 3: Complete Commands (Copy-Paste Ready)

Replace `YOUR_USERNAME` and `YOUR_REPO_NAME` with your actual GitHub username and repository name:

```bash
git init
git add .
git commit -m "Initial commit: Fire Detection and Prevention Backend"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

## Alternative: Using SSH (if you have SSH keys set up)

```bash
git init
git add .
git commit -m "Initial commit: Fire Detection and Prevention Backend"
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

## Step 4: Authentication

When you run `git push`, GitHub will ask for authentication:

**Option A: Personal Access Token (Recommended)**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Select scopes: `repo` (full control)
4. Copy the token
5. When prompted for password, paste the token

**Option B: GitHub CLI**
```bash
# Install GitHub CLI, then:
gh auth login
```

**Option C: SSH Keys**
1. Generate SSH key: `ssh-keygen -t ed25519 -C "your_email@example.com"`
2. Add to GitHub: Settings → SSH and GPG keys → New SSH key
3. Use SSH URL: `git@github.com:USERNAME/REPO.git`

## Troubleshooting

### If you get "fatal: remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### If you need to update the remote URL
```bash
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### If you get authentication errors
- Make sure you're using a Personal Access Token (not your password)
- Or set up SSH keys

### If files are too large
- Check `.gitignore` is working (should ignore `env/`, `__pycache__/`, etc.)
- Large files should be in `.gitignore`

## After Pushing

1. **Refresh your GitHub repository page** - you should see all your files
2. **Add repository description** (click gear icon next to "About")
3. **Add topics/tags** for better discoverability
4. **Update README** if needed

## Future Updates

To push future changes:

```bash
git add .
git commit -m "Description of your changes"
git push
```

## Quick Reference

```bash
# Check status
git status

# See what files changed
git diff

# View commit history
git log

# Pull latest changes (if working with others)
git pull
```

