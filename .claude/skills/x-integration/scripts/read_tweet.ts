#!/usr/bin/env npx tsx
/**
 * X Integration - Read Tweet & Replies
 * Usage: echo '{"tweetUrl":"https://x.com/elonmusk/status/123"}' | npx tsx read_tweet.ts
 */

import { getBrowserContext, navigateToTweet, runScript, config, ScriptResult } from '../lib/browser.js';

interface ReadInput {
    tweetUrl: string;
}

async function readTweet(input: ReadInput): Promise<ScriptResult> {
    const { tweetUrl } = input;

    if (!tweetUrl) {
        return { success: false, message: 'Tweet URL cannot be empty' };
    }

    let context = null;
    try {
        context = await getBrowserContext();
        const navResult = await navigateToTweet(context, tweetUrl);

        if (!navResult.success) {
            return { success: false, message: navResult.error || 'Failed to navigate to tweet' };
        }

        const page = navResult.page;

        // Check if we hit login wall
        const isLoginWall = await page.locator('input[autocomplete="username"]').isVisible().catch(() => false);
        if (isLoginWall) {
            return { success: false, message: 'X restricted access to this tweet. Run /x-integration to re-authenticate or check your account status.' };
        }

        // Twitter's UI is highly dynamic and uses React. Sometimes the article and User-Name
        // are present, but the tweetText hasn't been mounted yet. We wait a bit to let the
        // DOM settle before we try to extract texts.
        await page.waitForTimeout(2000);

        const threadData = await page.evaluate(() => {
            const articleNodes = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            if (articleNodes.length === 0) return null;

            return articleNodes.map(node => {
                const authorEl = node.querySelector('[data-testid="User-Name"]');
                const authorInfo = authorEl ? authorEl.textContent : 'Unknown';

                let handle = '';
                const links = Array.from(authorEl?.querySelectorAll('a') || []);
                const handleLink = (links as HTMLAnchorElement[]).find(a => a.href.includes('/'))?.getAttribute('href');
                if (handleLink) {
                    handle = handleLink.split('/')[1];
                } else {
                    const handleMatch = authorInfo?.match(/@(\w+)/);
                    if (handleMatch) handle = handleMatch[1];
                }

                let textEl = node.querySelector('[data-testid="tweetText"]');
                if (!textEl) {
                    textEl = node.querySelector('div[lang]');
                }

                let text = '';
                if (textEl) {
                    text = textEl.innerHTML.replace(/<br>/g, '\n').replace(/<[^>]*>?/gm, '');
                } else {
                    text = (node as HTMLElement).innerText || '';
                }

                const timeEl = node.querySelector('time');
                const timestamp = timeEl ? timeEl.getAttribute('datetime') : null;

                const rawPhotos = Array.from(node.querySelectorAll('[data-testid="tweetPhoto"] img, img[alt="Image"], img[src*="media"], img'));
                const photos = Array.from(new Set(rawPhotos
                    .map(img => (img as HTMLImageElement).src)
                    .filter(src => src && !src.includes('profile_images') && (src.includes('format=jpg') || src.includes('format=png') || src.includes('.jpg') || src.includes('.png')))));

                const viewsEl = node.querySelector('a[href*="/analytics"]') || node.querySelector('[aria-label*="View"], [aria-label*="查看"]');
                let views = viewsEl ? (viewsEl as HTMLElement).innerText.trim() : null;
                if (views === '') views = '0';

                const likesEl = node.querySelector('[data-testid="like"], [data-testid="unlike"]');
                let likes = likesEl ? (likesEl as HTMLElement).innerText.trim() : null;
                if (likes === '') likes = '0';

                const retweetsEl = node.querySelector('[data-testid="retweet"], [data-testid="unretweet"]');
                let retweets = retweetsEl ? (retweetsEl as HTMLElement).innerText.trim() : null;
                if (retweets === '') retweets = '0';

                const repliesEl = node.querySelector('[data-testid="reply"]');
                let replies = repliesEl ? (repliesEl as HTMLElement).innerText.trim() : null;
                if (replies === '') replies = '0';

                return {
                    author: authorInfo,
                    handle,
                    text,
                    timestamp,
                    photos: photos.length > 0 ? photos : undefined,
                    metrics: { views, likes, retweets, replies }
                };
            }).filter(t => t.text.length > 0);
        });

        if (!threadData || threadData.length === 0) {
            return { success: false, message: 'Failed to extract tweet content. The page layout might have changed or results are empty.' };
        }

        return {
            success: true,
            message: `Successfully read tweet and ${threadData.length - 1} replies.`,
            data: {
                main_tweet: threadData[0],
                context_or_replies: threadData.slice(1)
            }
        };

    } finally {
        if (context) await context.close();
    }
}

runScript<ReadInput>(readTweet);
