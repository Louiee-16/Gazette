from itertools import chain

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from django.db.models.functions import ExtractYear
from .models import Document, LegacyDocument, Session
from .models import PublicComment

 
def gazette_index(request):
    """Public index of all approved measures, plus archived legacy bills."""
    docs = Document.objects.filter(status='APPROVED')
    legacy_docs = LegacyDocument.objects.all()

    # Filters
    search_query = request.GET.get('search', '').strip()
    type_filter  = request.GET.get('type', '').strip()
    year_filter  = request.GET.get('year', '').strip()

    if search_query:
        docs = docs.filter(
            Q(title__icontains=search_query) |
            Q(reference_no__icontains=search_query) |
            Q(content__icontains=search_query)
        )
        legacy_docs = legacy_docs.filter(
            Q(title__icontains=search_query) |
            Q(reference_no__icontains=search_query) |
            Q(extracted_text__icontains=search_query)
        )
    if type_filter and type_filter != 'ALL':
        docs = docs.filter(doc_type=type_filter)
        legacy_docs = legacy_docs.filter(doc_type=type_filter)
    if year_filter:
        docs = docs.filter(updated_at__year=year_filter)
        legacy_docs = legacy_docs.filter(year=year_filter)

    # Available years for dropdown, across both sources
    doc_years = set(
        Document.objects.filter(status='APPROVED')
        .annotate(year=ExtractYear('updated_at'))
        .values_list('year', flat=True)
        .distinct()
    )
    legacy_years = set(
        LegacyDocument.objects.exclude(year__isnull=True)
        .values_list('year', flat=True)
        .distinct()
    )
    available_years = sorted(doc_years | legacy_years, reverse=True)

    # Merge and sort in Python since the two sources don't share a schema
    combined = sorted(chain(docs, legacy_docs), key=lambda d: d.updated_at, reverse=True)

    # Paginate
    paginator = Paginator(combined, 20)
    page = request.GET.get('page', 1)
    documents = paginator.get_page(page)
 
    return render(request, 'gazette/gazette_index.html', {
        'documents':       documents,
        'search_query':    search_query,
        'type_filter':     type_filter,
        'year_filter':     year_filter,
        'available_years': available_years,
    })
 
 
def public_participation_document(request, doc_id):
    """Individual document page with full text and comments."""
    doc = get_object_or_404(Document, id=doc_id)
    comments = PublicComment.objects.filter(document=doc, tag = "comment")
    replies = PublicComment.objects.filter(document= doc.id, tag="reply")
 
    # Related documents — same committee or same author, excluding current
    related = Document.objects.filter(
        status='APPROVED'
    ).exclude(id=doc.id).filter(
        Q(referred_committee=doc.referred_committee) |
        Q(author=doc.author)
    ).distinct()[:4]
 
    comment_submitted = request.session.pop('comment_submitted', False)
 
    return render(request, 'Documents/PPdocument.html', {
        'doc':doc,
        'comments':comments,
        'related':related,
        'comment_submitted': comment_submitted,
        'replies': replies,
    })
 
 
def gazette_document(request, doc_id):
    """Individual document page with full text and comments."""
    doc = get_object_or_404(Document, id=doc_id)
    comments = PublicComment.objects.filter(document=doc, tag = "comment")
    replies = PublicComment.objects.filter(document= doc.id, tag="reply")
 
    # Related documents — same committee or same author, excluding current
    related = Document.objects.filter(
        status='APPROVED'
    ).exclude(id=doc.id).filter(
        Q(referred_committee=doc.referred_committee) |
        Q(author=doc.author)
    ).distinct()[:4]
 
    comment_submitted = request.session.pop('comment_submitted', False)
 
    return render(request, 'Documents/gazette_document.html', {
        'doc':doc,
        'comments':comments,
        'related':related,
        'comment_submitted': comment_submitted,
        'replies': replies,
    })



def gazette_legacy_document(request, doc_id):
    """Detail page for an archived legacy bill (pre-system or scanned copy)."""
    doc = get_object_or_404(LegacyDocument, id=doc_id)

    related = LegacyDocument.objects.filter(doc_type=doc.doc_type).exclude(id=doc.id)[:4]

    return render(request, 'Documents/legacy_document.html', {
        'doc': doc,
        'related': related,
    })


def gazette_submit_comment(request, doc_id):
    """Handle public comment submission."""
    doc = get_object_or_404(Document, id=doc_id)
 
    if request.method != 'POST':
        return redirect('gazette_document', doc_id=doc_id)
 
    if not doc.public_participation:
        messages.error(request, 'Public comment is closed for this measure.')
        return redirect('gazette_document', doc_id=doc_id)
 
    name    = request.POST.get('name', '').strip()
    barangay = request.POST.get('barangay', '').strip()
    comment = request.POST.get('comment', '').strip()
 
    if not name or not comment:
        messages.error(request, 'Name and comment are required.')
        return redirect('public-participation-document', doc_id=doc_id)
 
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')
    parent_id = request.POST.get('parent_id')
    parent = None

    if (parent_id):
        tag = "reply"
        parent = PublicComment.objects.get(id = parent_id)
    PublicComment.objects.create(
        document=doc,
        name=name,
        barangay=barangay,
        comment=comment,
        ip_address=ip,
        is_approved=False,
        tag = "reply" if parent_id else "comment",
        replyTo = parent if parent_id else None

    )
 
    request.session['comment_submitted'] = True
    return redirect('public-participation-document', doc_id=doc_id)
 
 
def gazette_download(request, doc_id):
    """Download document as PDF."""
    doc = get_object_or_404(Document, id=doc_id, status='APPROVED')
    html_string = render_to_string('documents/document_pdf.html', {'doc': doc})
 
    try:
        from xhtml2pdf import pisa
        import io
        import re
 
        html_string = re.sub(r'<p[^>]*>\s*<br\s*/?>\s*</p>', '', html_string)
 
        buffer = io.BytesIO()
        pisa.CreatePDF(html_string, dest=buffer)
        buffer.seek(0)
 
        filename = f"{doc.doc_type}-{doc.reference_no or doc.id}-{doc.updated_at.year}.pdf"
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
 
    except ImportError:
        return HttpResponse('PDF generation unavailable.', status=500)
 
 
def gazette_hearings(request):

    open_docs = Document.objects.filter(
        public_participation=True, status='REFERRED').order_by('-updated_at')
 
    upcoming_sessions = Session.objects.filter(
        session_date__gte=timezone.now().date()
    ).order_by('session_date')[:5]
 
    return render(request, 'gazette/gazette_hearings.html', {
        'open_docs':         open_docs,
        'upcoming_sessions': upcoming_sessions,
    })
 
 