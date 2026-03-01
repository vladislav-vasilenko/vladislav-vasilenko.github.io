export function showLocalToast(message: string, target: HTMLElement): void {
    const existing = document.querySelector('.toast--local');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast toast--local';
    toast.textContent = message;
    document.body.appendChild(toast);

    const rect = target.getBoundingClientRect();
    toast.style.top = `${rect.bottom + 10}px`;
    toast.style.left = `${rect.left + rect.width / 2}px`;

    requestAnimationFrame(() => {
        toast.classList.add('toast--visible');
    });

    setTimeout(() => {
        toast.classList.remove('toast--visible');
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

export function showToast(message: string): void {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('toast--visible');
    });

    setTimeout(() => {
        toast.classList.remove('toast--visible');
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}
