#!/usr/bin/env npx tsx
/**
 * X Integration - View User Profile & Recent Tweets
 * Usage: echo '{"username":"elonmusk", "maxTweets":10}' | npx tsx view_profile.ts
 */

import { getBrowserContext, runScript, config, ScriptResult } from '../lib/browser.js';

interface ProfileInput {
    username: string;
    maxTweets?: number;
}

async function viewProfile(input: ProfileInput): Promise<ScriptResult> {
    const { username } = input;
    const maxTweets = input.maxTweets || 5;

    if (!username || username.trim().length === 0) {
        return { success: false, message: 'Username cannot be empty' };
    }

    // Remove @ if user included it
    const cleanUsername = username.replace(/^@/, '').trim();

    let context = null;
    try {
        context = await getBrowserContext();
        const page = context.pages()[0] || await context.newPage();

        const profileUrl = `https://x.com/${cleanUsername}`;
        await page.goto(profileUrl, { timeout: config.timeouts.navigation, waitUntil: 'domcontentloaded' });

        // Check if account is suspended or doesn't exist
        try {
            await Promise.race([
                page.waitForSelector('[data-testid="emptyState"]', { timeout: config.timeouts.elementWait }),
                page.waitForSelector('article[data-testid="tweet"]', { timeout: config.timeouts.elementWait }),
                page.waitForSelector('[data-testid="UserName"]', { timeout: config.timeouts.elementWait })
            ]);
        } catch (e) {
            await page.waitForTimeout(config.timeouts.pageLoad);
        }

        const isEmptyState = await page.locator('[data-testid="emptyState"]').isVisible().catch(() => false);
        if (isEmptyState) {
            return { success: false, message: `Account @${cleanUsername} doesn't exist, is suspended, or tweets are protected.` };
        }

        // Extract Profile Info
        const profileInfo = await page.evaluate(() => {
            const nameEl = document.querySelector('[data-testid="UserName"]');
            const name = nameEl ? nameEl.textContent : 'Unknown';

            const descEl = document.querySelector('[data-testid="UserDescription"]');
            const description = descEl ? descEl.textContent : '';

            const locationEl = document.querySelector('[data-testid="UserLocation"]');
            const location = locationEl ? locationEl.textContent : null;

            const urlEl = document.querySelector('[data-testid="UserUrl"]');
            const url = urlEl ? urlEl.getAttribute('href') : null;

            // Follower counts
            const followingEl = document.querySelector('a[href$="/following"]');
            const following = followingEl ? followingEl.textContent : null;

            const followersEl = document.querySelector('a[href$="/verified_followers"]');
            const followers = followersEl ? followersEl.textContent : null;

            return {
                name,
                description,
                location,
                url,
                stats: {
                    following,
                    followers
                }
            };
        });

        // Scroll and collect tweets until we reach maxTweets or can't find more
        const tweetsList = [];
        const seenTweetLinks = new Set();

        let scrollAttempts = 0;
        const maxScrolls = Math.ceil(maxTweets / 3) + 2; // Roughly 3 tweets per viewport

        while (tweetsList.length < maxTweets && scrollAttempts < maxScrolls) {
            const currentBatch = await page.evaluate((username) => {
                const tweetNodes = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                return tweetNodes.map(node => {
                    // Determine if it's a pinned tweet, retweet, or regular tweet
                    let type = 'tweet';
                    const socialContext = node.querySelector('[data-testid="socialContext"]');
                    if (socialContext) {
                        if (socialContext.textContent?.toLowerCase().includes('pinned')) type = 'pinned';
                        else if (socialContext.textContent?.toLowerCase().includes('reposted')) type = 'repost';
                        else if (socialContext.textContent?.toLowerCase().includes('replied')) type = 'reply';
                    }

                    // Extract content
                    const textEl = node.querySelector('[data-testid="tweetText"]');
                    const text = textEl ? textEl.innerHTML.replace(/<br>/g, '\n').replace(/<[^>]*>?/gm, '') : '';

                    // Extract timestamp
                    const timeEl = node.querySelector('time');
                    const timestamp = timeEl ? timeEl.getAttribute('datetime') : null;

                    // Try to construct URL
                    const tweetLinks = Array.from(node.querySelectorAll('a[href*="/status/"]'));
                    const tweetUrlPath = tweetLinks.length > 0 ? tweetLinks[0].getAttribute('href') : null;
                    const url = tweetUrlPath ? `https://x.com${tweetUrlPath}` : null;

                    // Get metrics if possible
                    const viewsStr = node.querySelector('[aria-label*="View"]')?.getAttribute('aria-label') || '';
                    const viewsMatch = viewsStr.match(/([\d,]+|\w+)\s+View/i);
                    const views = viewsMatch ? viewsMatch[1] : null;

                    const likesStr = node.querySelector('[data-testid="like"]')?.getAttribute('aria-label') || '';
                    const likesMatch = likesStr.match(/([\d,]+)\s+Like/i);
                    const likes = likesMatch ? likesMatch[1] : null;

                    const retweetsStr = node.querySelector('[data-testid="retweet"]')?.getAttribute('aria-label') || '';
                    const retweetsMatch = retweetsStr.match(/([\d,]+)\s+Retweet/i);
                    const retweets = retweetsMatch ? retweetsMatch[1] : null;

                    const repliesStr = node.querySelector('[data-testid="reply"]')?.getAttribute('aria-label') || '';
                    const repliesMatch = repliesStr.match(/([\d,]+)\s+Repl/i);
                    const replies = repliesMatch ? repliesMatch[1] : null;

                    return {
                        type,
                        text,
                        timestamp,
                        url,
                        metrics: { views, likes, retweets, replies }
                    };
                }).filter(t => t.url !== null);
            }, cleanUsername);

            // Add new tweets to the list
            for (const tweet of currentBatch) {
                if (tweet.url && !seenTweetLinks.has(tweet.url) && tweetsList.length < maxTweets) {
                    seenTweetLinks.add(tweet.url);
                    tweetsList.push(tweet);
                }
            }

            if (tweetsList.length >= maxTweets) {
                break;
            }

            // Scroll down
            await page.evaluate(() => window.scrollBy(0, document.body.scrollHeight || 1500));
            await page.waitForTimeout(1500); // Wait for new tweets to load
            scrollAttempts++;
        }

        return {
            success: true,
            message: `Successfully fetched profile @${cleanUsername} and ${tweetsList.length} recent tweets.`,
            data: {
                profile: profileInfo,
                tweets: tweetsList
            }
        };

    } finally {
        if (context) await context.close();
    }
}

runScript<ProfileInput>(viewProfile);
