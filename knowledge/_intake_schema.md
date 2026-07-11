# 접수 슬롯 스키마

접수 면담 봇이 채워야 할 슬롯을 선언한다. 트랙(정서/관계/위기) 판별이 최우선
슬롯이고, 공통 슬롯 4종과 트랙별 조건부 슬롯이 뒤따른다. 위기 트랙의 계획·수단
슬롯은 `red_flag: true`로 표시해 다른 슬롯보다 먼저 질문되도록 한다.

근거: `접수-면접-질문지-구성.md`(주요 영역 1~5), `위기-상황-스크리닝.md`(확인
항목 1·2).

```yaml
intake_schema:
  version: "1"
  opening_question: "오늘 상담을 받으러 오신 이유가 무엇인가요?"
  slots:
    - id: track
      label: 상담 트랙
      required: true
      priority: 0
      values: [정서, 관계, 위기]
      signals:
        정서: [우울, 불안, 잠]
        관계: [남편, 부부, 가족, 갈등]
        위기: [자해, 죽고 싶]
    - id: chief_complaint
      label: 호소 문제
      required: true
      priority: 1
    - id: coping
      label: 대처 시도
      required: false
      priority: 2
      signals: [대처, 해봤어요, 노력]
    - id: support
      label: 지지체계
      required: false
      priority: 3
      signals: [가족, 친구, 직장]
    - id: expectation
      label: 상담 기대
      required: false
      priority: 4
      signals: [기대, 원하는, 바라는]
    - id: symptom_context
      label: 증상 시기·일상 영향
      required: false
      priority: 5
      when: "track=정서"
      signals: [언제부터, 얼마나 자주, 어떤 상황]
    - id: relationship_context
      label: 관계 대상·기간
      required: false
      priority: 5
      when: "track=관계"
      signals: [누구와, 얼마나 됐, 얼마나 만났]
    - id: crisis_attempt_history
      label: 자해·자살 시도 이력
      required: false
      priority: 5
      when: "track=위기"
      signals: [시도한 적, 생각한 적, 자살]
    - id: crisis_plan_means
      label: 자해 계획·수단
      required: false
      priority: 6
      when: "track=위기"
      red_flag: true
      signals: [계획, 방법, 수단]
```
