# Mudarrisi Physics Validator

مدقق مستقل لبنوك أسئلة الفيزياء العراقية. الهدف: **منع PASS الذاتي غير المثبت**.

## قاعدة القبول

- خطأ يمكن إثباته آليًا → `FAIL`.
- فحص علمي/دلالي مطلوب لكن دليله غير موجود → `UNVERIFIED`.
- `PASS` لا يظهر افتراضيًا إلا بوجود دليل المصدر ومراجعة دلالية مستقلة مكتملة.

## الفحوص الحالية

- بنية JSON وصيغتي `mcq` و`true_false`.
- MCQ = أربعة خيارات بالضبط.
- صحة `correctAnswer` وعدد التفسيرات.
- منع الأسئلة والخيارات المكررة.
- منع الإحالات مثل «وفق الصورة / في المصدر / في الملزمة».
- قاعدة الدفعات: غير الأخيرة = 30، والأخيرة ≤ 30 عند وجود metadata.
- تمثيل الأسئلة الأصلية من `manifest`.
- مطابقة المنطوق الحرفي عندما يكون `literal_required=true`.
- غياب المصدر أو المراجعة الدلالية المطلوبة لا ينتج PASS.

## الخصوصية

هذا المستودع Public ويحتوي **الكود والأمثلة الوهمية فقط**. لا تُحفظ فيه صور المنهج أو بنك حقيقي أو بيانات شخصية. الربط مع Google Drive سيستخدم أسرار GitHub Actions، ولا يجب وضع أي credential في commit أو logs.

## تشغيل

```bash
python validator.py \
  --bank bank.json \
  --manifest manifest.json \
  --semantic-review semantic_review.json \
  --config config.example.json \
  --output result.json
```

Exit code = 0 عند PASS فقط؛ `FAIL` و`UNVERIFIED` يرجعان non-zero حتى لا يمر CI بصمت.

## الحالة

V1 foundation: deterministic validator + fail-closed semantic/source evidence policy + CI self-tests.
