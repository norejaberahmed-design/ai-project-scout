# دورة اقتراح المهارات المراجَعة

بعد دمج workflow في main، يمكنه اقتراح مهارة داخلية جديدة تلقائيًا عبر GitHub Actions، لكنه لا ينشّطها ولا يدمجها بنفسه.

## التهيئة مرة واحدة
في Settings → Secrets and variables → Actions أضف:
- Repository secret: SCOUT_LLM_API_KEY (مفتاح مزود نموذج متوافق مع OpenAI Chat Completions).
- Repository variable: SCOUT_LLM_MODEL (اسم نموذج مسموح في حساب المزود).
- Repository variable: SCOUT_ENABLE_SKILL_PROPOSER=true لتفعيل التشغيل المجدول الأسبوعي.

إذا لم تُضبط المتغيرات، تتخطى المهمة إنشاء المقترح. لا تضع أي مفتاح في ملفات المستودع أو واجهة Pages.

## التشغيل
من Actions → Reviewed Skill Proposal Cycle → Run workflow، فعّل run_proposer لتجربة مقترح واحد. يتولى workflow إنشاء تقرير فجوة، وتوليد ملف SKILL.md واحد تحت skills/proposed، وفحصه، وتشغيل كامل اختبارات الوحدة، ثم فتح Draft PR إذا نجحت الفحوصات. لا تُشغّل المهارة المرشحة ولا تُفعّلها آليًا.

## ما لا يثبته النجاح
نجاح الاختبارات يثبت اجتياز الفحوصات الآلية المحددة، ولا يثبت أن المهارة مفيدة في الإنتاج. يجب أن يراجع شخص محتواها ومصدرها ومخاطرها قبل دمجها، وبعد الدمج يجب اختبار أثرها في مهام فعلية. لا يتم دمج PR تلقائيًا.
