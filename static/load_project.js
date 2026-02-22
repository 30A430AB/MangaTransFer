window.projectPages = null;
window.projectDirectory = null;
window.currentImg = null;

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.position = 'fixed';
    toast.style.top = '20px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.padding = '12px 20px';
    toast.style.backgroundColor = type === 'success' ? '#4caf50' : (type === 'error' ? '#f44336' : '#2196f3');
    toast.style.color = 'white';
    toast.style.borderRadius = '4px';
    toast.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
    toast.style.zIndex = '9999';
    toast.style.fontSize = '14px';
    toast.style.transition = 'opacity 0.3s ease';
    toast.style.opacity = '1';
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 300);
    }, 3000);
}

window.selectProjectFile = function() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = function(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(ev) {
            const jsonData = ev.target.result;
            fetch('/load_project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: jsonData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showToast('Error: ' + data.error, 'error');
                    return;
                }
                window.projectPages = data.pages;
                window.projectDirectory = data.directory;
                window.currentImg = data.current_img;

                if (data.imageUrl) {
                    window.canvasControls.loadLayers(data.imageUrl, data.inpaintedImageUrl, data.textBlocks);
                    if (window.canvasControls.setRegions) {
                        window.canvasControls.setRegions(data.regions);
                    }
                } else {
                    console.warn('No imageUrl in response');
                }
                updateTextBlocks(data.textBlocks);
                if (data.thumbnails && data.thumbnails.length > 0) {
                    generateThumbnails(data.thumbnails, data.directory);
                } else {
                    console.warn('No thumbnails received');
                }
            })
            .catch(err => {
                console.error('Error loading project:', err);
                showToast('Failed to load project', 'error');
            });
        };
        reader.readAsText(file);
    };
    input.click();
};

function generateThumbnails(thumbnails, directory) {
    const container = document.querySelector('[name="thumbnail-list"]');
    if (!container) {
        console.error('Thumbnail container not found');
        return;
    }
    container.innerHTML = '';
    const innerDiv = document.createElement('div');
    innerDiv.className = 'thumbnail-container';
    thumbnails.forEach(item => {
        const key = item.key;
        const thumbUrl = item.thumb_url;
        const card = document.createElement('div');
        card.className = 'thumbnail-card';
        card.setAttribute('data-key', key);
        const img = document.createElement('img');
        img.className = 'thumbnail-image';
        img.src = thumbUrl;
        img.alt = `缩略图${key}`;
        card.appendChild(img);
        const numberDiv = document.createElement('div');
        numberDiv.style.position = 'absolute';
        numberDiv.style.bottom = '4px';
        numberDiv.style.left = '0';
        numberDiv.style.right = '0';
        numberDiv.style.color = 'black';
        numberDiv.style.textAlign = 'center';
        numberDiv.style.padding = '2px 0';
        numberDiv.style.fontSize = 'clamp(10px, 2vw, 15px)';
        numberDiv.textContent = key;
        card.appendChild(numberDiv);
        card.addEventListener('click', () => loadImage(key, directory));
        innerDiv.appendChild(card);
    });
    container.appendChild(innerDiv);
}

function loadImage(key, directory) {
    if (window.canvasControls && window.canvasControls.updateCurrentPageData) {
        window.canvasControls.updateCurrentPageData();
    }

    console.log('loadImage called with key:', key, 'directory:', directory);
    const entries = window.projectPages ? window.projectPages[key] : [];
    console.log('entries for this key:', entries);
    fetch('/get_image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory: directory, key: key, entries: entries })
    })
    .then(response => response.json())
    .then(data => {
        if (data.originalImageUrl) {
            window.currentImg = key;
            window.canvasControls.loadLayers(data.originalImageUrl, data.inpaintedImageUrl, data.textBlocks);
            updateTextBlocks(data.textBlocks, entries, key);
        } else {
            showToast('加载图片失败：' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(err => {
        console.error('Error loading image:', err);
        showToast('加载图片失败', 'error');
    });
}

function updateTextBlocks(textBlocks, entries, pageKey) {
    const countElement = document.getElementById('text-block-count');
    if (countElement) {
        countElement.textContent = `文本块 (${textBlocks.length})`;
    }
    const container = document.getElementById('text-block-list');
    if (!container) return;
    container.innerHTML = '';

    textBlocks.forEach((block, index) => {
        const entry = entries ? entries[index] : null;

        const card = document.createElement('div');
        card.className = 'text-block-card';
        card.setAttribute('data-index', index);

        const imageDiv = document.createElement('div');
        imageDiv.className = 'text-block-image';
        const img = document.createElement('img');
        img.src = block.imageUrl;
        img.alt = `文本块${index+1}`;
        imageDiv.appendChild(img);
        card.appendChild(imageDiv);

        const footerDiv = document.createElement('div');
        footerDiv.className = 'text-block-footer';

        const eyeBtn = document.createElement('div');
        eyeBtn.className = 'text-block-button';
        const initialIcon = block.visible ? 'visibility' : 'visibility_off';
        eyeBtn.innerHTML = `<span class="material-icons">${initialIcon}</span>`;
        eyeBtn.setAttribute('data-index', index);

        eyeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const newVisible = !block.visible;
            block.visible = newVisible;
            if (window.projectPages && pageKey && entry) {
                entry.matched = newVisible ? 1 : 0;
            }
            eyeBtn.innerHTML = `<span class="material-icons">${newVisible ? 'visibility' : 'visibility_off'}</span>`;
            if (window.canvasControls.setTextBlockVisibility) {
                window.canvasControls.setTextBlockVisibility(index, newVisible);
            }
        });

        footerDiv.appendChild(eyeBtn);
        card.appendChild(footerDiv);
        container.appendChild(card);
    });
}

window.loadProjectFromData = function(data) {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    fetch('/load_project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast('Error: ' + data.error, 'error');
            return;
        }
        window.projectPages = data.pages;
        window.projectDirectory = data.directory;
        window.currentImg = data.current_img;

        if (data.imageUrl) {
            window.canvasControls.loadLayers(data.imageUrl, data.inpaintedImageUrl, data.textBlocks);
            if (window.canvasControls.setRegions) {
                window.canvasControls.setRegions(data.regions);
            }
        } else {
            console.warn('No imageUrl in response');
        }
        updateTextBlocks(data.textBlocks);
        if (data.thumbnails && data.thumbnails.length > 0) {
            generateThumbnails(data.thumbnails, data.directory);
        } else {
            console.warn('No thumbnails received');
        }
    })
    .catch(err => {
        console.error('Error loading project from data:', err);
        showToast('Failed to load project', 'error');
    });
};

window.saveProject = function() {
    if (window.canvasControls && window.canvasControls.updateCurrentPageData) {
        window.canvasControls.updateCurrentPageData();
    }

    if (!window.projectDirectory || !window.projectPages || !window.currentImg) {
        showToast('没有可保存的项目', 'error');
        return;
    }

    const directory = window.projectDirectory;
    const key = window.currentImg;
    const entries = window.projectPages[key];

    const jsonPayload = {
        directory: directory,
        pages: window.projectPages,
        current_img: key
    };

    fetch('/save_project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(jsonPayload)
    })
    .then(response => response.json())
    .then(result => {
        if (!result.success) {
            throw new Error('保存 JSON 失败：' + (result.error || '未知错误'));
        }
        return saveImages(directory, key, entries);
    })
    .then(() => {
        showToast('保存成功', 'success');
    })
    .catch(err => {
        console.error('保存出错:', err);
        showToast('保存失败：' + err.message, 'error');
    });
};

async function saveImages(directory, key, entries) {
    let imageToSave = null;
    if (inpaintedImage) {
        imageToSave = inpaintedImage;
    } else if (comicImage) {
        imageToSave = comicImage;
    }
    if (imageToSave) {
        const imageDataURL = imageToSave.toDataURL({ format: 'png' });
        const imageBlob = dataURItoBlob(imageDataURL);
        const formData = new FormData();
        formData.append('directory', directory);
        formData.append('key', key);
        formData.append('image', imageBlob, key + '.png');
        const response = await fetch('/save_inpainted', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        if (!result.success) {
            throw new Error('保存 inpainted 失败：' + (result.error || '未知错误'));
        }
    }

    const resultPayload = {
        directory: directory,
        key: key,
        entries: entries
    };
    const resResponse = await fetch('/save_result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resultPayload)
    });
    const resResult = await resResponse.json();
    if (!resResult.success) {
        throw new Error('保存结果图失败：' + (resResult.error || '未知错误'));
    }
}
