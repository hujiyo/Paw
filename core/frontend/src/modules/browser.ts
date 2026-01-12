
import { $ } from './utils.js';

export class Browser {
    private static iframe: HTMLIFrameElement;
    private static input: HTMLInputElement;
    private static goBtn: HTMLButtonElement;

    static init() {
        this.iframe = $<HTMLIFrameElement>('#browser-frame')!;
        this.input = $<HTMLInputElement>('#browser-url')!;
        this.goBtn = $<HTMLButtonElement>('#browser-go')!;
        
        this.goBtn.addEventListener('click', () => this.navigate());
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.navigate();
        });
    }

    static navigate(url?: string) {
        let target = url || this.input.value.trim();
        if (!target) return;
        
        if (!target.startsWith('http://') && !target.startsWith('https://')) {
            target = 'http://' + target;
        }
        
        this.input.value = target;
        this.iframe.src = target;
    }
}
