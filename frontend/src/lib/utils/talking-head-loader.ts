// dynamic TalkingHead loader
export async function loadTalkingHead() {
  const module = await import('../vendor/talkinghead.js');
  return new module.TalkingHead();
}
