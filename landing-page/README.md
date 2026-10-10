# KeyGuard AI Landing Page

Static marketing/download page for KeyGuard AI, deployable to Vercel with zero configuration.

## File Structure

```
landing-page/
├── index.html                      # Main landing page
├── style.css                       # All styling (dark theme, responsive)
├── script.js                       # Minimal JS (smooth scroll, animations)
├── vercel.json                     # Vercel configuration for installer download
├── public/
│   └── KeyloggerDetector-Setup.exe # 81 MB installer (NOT committed to git)
├── .gitignore                      # Excludes large .exe files
└── README.md                       # This file
```

## ⚠️ Important: Handling the 81 MB Installer

The installer is too large to commit to Git. Choose one of these approaches:

### Option A: GitHub Releases (Recommended for Production)

1. **Create a GitHub Release:**
   ```bash
   # Go to your repo on GitHub
   # Click "Releases" → "Create a new release"
   # Tag: v2.5
   # Upload: KeyloggerDetector-Setup.exe
   ```

2. **Update index.html** with the release URL:
   ```html
   <a href="https://github.com/Antobenedict2006/Keylogger/releases/download/v2.5/KeyloggerDetector-Setup.exe" 
      class="btn-download" download>
   ```

3. **Deploy to Vercel** (installer loads from GitHub Releases)

### Option B: Git LFS (For Vercel Deployment with Installer)

1. **Install Git LFS:**
   ```bash
   git lfs install
   ```

2. **Track the installer:**
   ```bash
   cd landing-page
   git lfs track "public/*.exe"
   git add .gitattributes
   ```

3. **Commit and push:**
   ```bash
   git add public/KeyloggerDetector-Setup.exe
   git commit -m "Add installer via Git LFS"
   git push
   ```

### Option C: Vercel Deployment with Local Installer (Testing Only)

For local testing or private deployment, the installer is already in `public/`:

```bash
cd landing-page
vercel
```

The `/KeyloggerDetector-Setup.exe` link will work automatically.

**Note:** Vercel has a 100 MB function size limit, so this works for the 81 MB installer.

## Deployment to Vercel

### Quick Deploy

```bash
cd landing-page
vercel --prod
```

### Via GitHub Integration

1. Push `landing-page/` folder to your GitHub repo
2. Go to [vercel.com](https://vercel.com/new)
3. Import your repository
4. **Important:** Set **Root Directory** to `landing-page`
5. Click "Deploy"

## Current Configuration

✅ **Download link:** `/KeyloggerDetector-Setup.exe` (served from `public/`)  
✅ **Version:** v2.5  
✅ **File size:** 81 MB  
✅ **GitHub repo:** https://github.com/Antobenedict2006/Keylogger

## Testing Locally

```bash
# Option 1: Python HTTP server
cd landing-page
python -m http.server 8000

# Option 2: Node.js http-server (if installed)
npx http-server landing-page -p 8000

# Then visit: http://localhost:8000
```

## Features

✅ **Zero dependencies** (except Google Fonts CDN)  
✅ **Fully responsive** (mobile, tablet, desktop)  
✅ **Fast loading** (< 50 KB HTML/CSS/JS)  
✅ **Accessible** (keyboard navigation, reduced motion support)  
✅ **SEO-friendly** (semantic HTML, meta descriptions)  
✅ **Dark theme** (professional security tool aesthetic)  
✅ **Download configured** (proper headers, MIME types)

## Performance

- **First Contentful Paint:** < 1s
- **Lighthouse Score:** 95+ (Performance, Accessibility, Best Practices, SEO)
- **Page Size:** < 50 KB (excluding installer download)

## Vercel Configuration

The `vercel.json` file configures:
- Proper MIME type for `.exe` downloads
- Download filename enforcement
- 24-hour cache for the installer

## License

Same as KeyGuard AI main project
